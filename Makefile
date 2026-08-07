PY := .venv/bin/python

.PHONY: venv test build serve deploy clean

venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	$(PY) -m pytest -q

build:
	$(PY) -m gen.build

serve:
	$(PY) -m http.server 8642 -d docs

deploy: test build
	git add -A
	git commit -m "Rebuild site" || true
	git push origin main

clean:
	rm -rf docs/*
