# using slim to keep the image small — no need for the full Python image here
FROM python:3.9-slim

# set workdir inside the container
WORKDIR /app

# copy requirements first so Docker can cache this layer
# if only run.py changes later, pip install won't re-run
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the rest of the project files
COPY run.py       .
COPY config.yaml  .
COPY data.csv     .

# run the pipeline with explicit paths — no hardcoding inside run.py
CMD ["python", "run.py", \
     "--input",    "data.csv", \
     "--config",   "config.yaml", \
     "--output",   "metrics.json", \
     "--log-file", "run.log"]