FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=7860

WORKDIR /app

# A Hugging Face Space keeps only this Dockerfile: the code is pulled from GitHub at build
# time, so pushing to main stays the one way the hosted demo changes.
RUN python -c "import io, tarfile, urllib.request; b = urllib.request.urlopen('https://codeload.github.com/sumyiabutt/civicroute_ai/tar.gz/refs/heads/main').read(); tarfile.open(fileobj=io.BytesIO(b)).extractall('/tmp/src', filter='data')" \
 && cp -a /tmp/src/civicroute_ai-main/. /app/ \
 && rm -rf /tmp/src \
 && pip install --no-cache-dir -r requirements.txt

EXPOSE 7860
CMD ["python", "start_demo.py"]
