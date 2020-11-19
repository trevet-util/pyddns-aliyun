import json
import os
import sys

import urllib3
import yaml
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.UpdateDomainRecordRequest import UpdateDomainRecordRequest
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdkcore.client import AcsClient

# 先获取允许目录下的记录文件用于核对IP是否已变化
run_path = os.getcwd()
# 判断配置文件是否存在
run_path += "/config.yml"


def init_config():
    global yaml_file_data
    global run_config_data
    global run_parameter_key_list
    # 判断配置文件是否存在,存在直接获取
    if os.path.exists(run_path):
        # 存在则取配置文件内容
        stream = open(run_path, 'r', encoding="utf-8")
        yaml_file_data = yaml.load(stream, Loader=yaml.FullLoader)
        stream.close()
        if not yaml_file_data:
            yaml_file_data = {}
    else:
        yaml_file_data['value'] = '169.255.255.255'

    # 获取配置优先级,优先获取启动配置上的参数,否找从配置文件获取
    # 从启动参数中获取相关配置信息
    # ak={accessKeyId} ac={accessSecret} subdomain={subdomain} regionId={cn-hangzhou}
    argv_list = sys.argv[1:]
    if len(argv_list) > 0:
        for parameter in argv_list:
            parameter_arr = parameter.split('=')
            for _key in run_parameter_key_list:
                if parameter_arr[0] == _key:
                    run_config_data[_key] = parameter_arr[1]
        yaml_file_data['authentication'] = run_config_data
    if run_config_data.get('ak') and run_config_data.get('ac'):
        # 从启动配置上获取到数据,则直接结束初始化
        return

    # 如果从启动参数中获取不到信息,则验证 config.yaml 中的数据是否存在 ak 相关信息
    yaml_authentication_data = yaml_file_data.get('authentication')
    if not yaml_authentication_data:
        raise Exception("error config.yaml not 'authentication' info!")
    if not yaml_authentication_data.get('ak') or not yaml_authentication_data.get('ac'):
        # ak 和 ac 任意一个为空,则为异常.程序终止
        raise Exception("error config.yaml not 'authentication' info!")
    else:
        for parameter in run_parameter_key_list:
            run_config_data[parameter] = yaml_authentication_data.get(parameter)


# 以下为初始化过程
run_parameter_key_list = ['ak', 'ac', 'domain', 'subdomain', 'regionId']
yaml_file_data = {}
# 运行时所持有的关键信息
run_config_data = {}
init_config()
# 配置文件选择的优先级,run_paramter > file


client = AcsClient(run_config_data.get('ak'), run_config_data.get('ac'), run_config_data.get('regionId'))


def listByDomain(_client: AcsClient, _Domain_str: str):
    """

    获取指定域名下所有解析列表
    :param _client:
    :param _Domain_str: 域名（例如：qq.com,必须是顶级域名）
    :return:
    """
    request = DescribeDomainRecordsRequest()
    request.set_accept_format('json')
    request.set_DomainName(_Domain_str)

    response = _client.do_action_with_exception(request)
    return json.loads(str(response, encoding='utf-8'))


def editByDomainRecords(_client: AcsClient, _Record_data: dict, _value: str):
    """
    修改解析记录
    :param _client:
    :param _Record_data: 通过获取列表得来的解析信息
    :param _value: 要修改的记录值
    :return:
    """
    request = UpdateDomainRecordRequest()
    request.set_accept_format('json')

    request.set_RecordId(_Record_data.get('RecordId'))
    request.set_RR(_Record_data.get("RR"))
    request.set_Type(_Record_data.get('Type'))
    request.set_Value(_value)

    try:
        response = _client.do_action_with_exception(request)
    except ServerException as exce_entity:
        if exce_entity.message == 'The DNS record already exists.':
            err_msg = "{RR} 解析已被修改为 {value} ,无需修改.".format(RR=_Record_data.get("RR"), value=_value)
        else:
            err_msg = "未知异常; 阿里云异常消息原文： " + exce_entity.message
        raise Exception(err_msg)
    return json.loads(str(response, encoding='utf-8'))


def getIPInfo() -> str:
    url = 'http://pv.sohu.com/cityjson?ie=utf-8'
    _result = urllib3.PoolManager().request('GET', url)
    ip_info_json: str = str(_result.data, encoding="utf-8").split("= ")[1]
    return json.loads(ip_info_json[:-1]).get("cip")


def edit_service(_client: AcsClient, ip_str: str, _domain: str, _subdomain: str):
    # start - 获取已有域名解析列表
    # 如果过程任何一步出错则都会抛出异常中止程序运行
    result = listByDomain(client, _domain)
    list = result.get("DomainRecords").get("Record")
    edit_data = None
    for data in list:
        if _subdomain == data.get("RR"):
            edit_data = data
            break

    if edit_data is None:
        raise Exception("错误！未找到对应的解析记录")
    # end - 获取已有域名解析列表
    # 已获得 'RecordId'

    editByDomainRecords(_client, edit_data, ip_str)
    yaml_file_data['value'] = ip_str
    _stream = open(run_path, 'w', encoding="utf-8")
    yaml.dump(yaml_file_data, _stream)
    _stream.close()
    print("""
修改完毕！
{RR}.{DomainName}, {Type}记录, TTL: {ttl}, {Line}线路, 记录值：{Value}
当前记录TTL为： {ttl} 全网解析最迟于 {ttl} 秒后刷新
    """.format(
        ttl=edit_data.get("TTL"),
        DomainName=edit_data.get("DomainName"),
        Line=edit_data.get("Line"),
        Value=edit_data.get("Value") + " 变更为 " + ip_str,
        Type=edit_data.get("Type"),
        RR=edit_data.get("RR")
    ))


# 此处事务过程
# 第一步获取外网IP
ip_str = getIPInfo()
if yaml_file_data.get("value") != ip_str:
    print("IP有变化")
    edit_service(client, ip_str, run_config_data.get('domain'), run_config_data.get('subdomain'))
else:
    print("IP没有变化,无需修改")
