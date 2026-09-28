.PHONY: install matrix seed run web web-install test eval scenarios demo clean

install:
	pip install -r requirements-dev.txt

matrix:
	python scripts/build_distance_matrix.py
	python scripts/build_road_network.py

seed:
	python scripts/seed_demo.py --n 90

run:
	uvicorn fairtriage.api:app --reload --port 8000

web-install:
	cd frontend && npm install

# the Next.js interface on :3000; needs `make run` going in another terminal
web:
	cd frontend && npm run dev

test:
	python -m pytest tests/ -q -p no:warnings

eval:
	python scripts/run_eval.py --split test

scenarios:
	python scripts/run_scenarios.py

demo: matrix seed run

# empties the MongoDB database (make seed also does this before seeding)
clean:
	python -c "from fairtriage import db; db.drop_all(); print('database emptied')"
