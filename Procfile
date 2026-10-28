web: uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --ws-max-size 65536 --proxy-headers --forwarded-allow-ips '*'
