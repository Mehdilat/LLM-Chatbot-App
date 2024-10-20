FROM python:3.12.4

ENV OPENAI_API_KEY=your_openai_api_key_here
ENV ANTHROPIC_API_KEY=your_anthropic_api_key_here

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY app ./app

RUN pip install -r requirements.txt

CMD ["streamlit", "run", "app/app.py"]