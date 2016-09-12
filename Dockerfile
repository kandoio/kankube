FROM python:3.5

COPY . /tmp/src

RUN pip install -U pip
RUN pip install --src /usr/local/src -r /tmp/src/requirements.txt
RUN pip install /tmp/src/

RUN rm -rf /tmp/src

WORKDIR /src
ENTRYPOINT ["/usr/local/bin/kankube"]
