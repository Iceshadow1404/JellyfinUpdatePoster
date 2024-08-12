FROM python:3.12

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY copy_files.sh /copy_files.sh
RUN chmod +x /copy_files.sh

CMD ["/copy_files.sh", "python", "main.py"]