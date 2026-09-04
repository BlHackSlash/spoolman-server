FROM python:3.9-slim
WORKDIR /app
COPY server.py .
RUN pip install flask requests
ENV BIND_PORT=5000
EXPOSE $BIND_PORT
CMD ["python", "server.py"]
