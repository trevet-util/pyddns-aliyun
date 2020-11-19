FROM python:3.9.0
MAINTAINER Trevet-2020-11-17
# ENV https_proxy http://192.168.32.73:233
RUN pip3 install -i https://mirrors.aliyun.com/pypi/simple/ pip
RUN pip3 install PyYaml requests aliyun-python-sdk-alidns
COPY main.py /home
WORKDIR /home
ENTRYPOINT python3 main.py ak=$ak ac=$ac domain=$domain subdomain=$subdomain regionId=$regionId