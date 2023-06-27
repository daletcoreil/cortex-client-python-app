FROM python:3

WORKDIR /usr/src/sdk
COPY ./build/gen-sdk/python .
RUN python setup.py install

WORKDIR /usr/src/app
COPY ./client-app/python/. .
RUN python setup.py install

# CMD ["python", "-u", "main.py"]
CMD ["sleep", "infinity"]