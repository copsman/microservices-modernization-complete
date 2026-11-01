FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/ common/
ARG SERVICE_DIR
COPY ${SERVICE_DIR}/ /tmp/service/
RUN cp /tmp/service/main.py /code/main.py \
    && if [ -d /tmp/service/static ]; then cp -r /tmp/service/static /code/static; fi \
    && rm -rf /tmp/service
CMD ["python","main.py"]
