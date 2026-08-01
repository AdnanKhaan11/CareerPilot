.PHONY: run dashboard telegram voice eval eval-judge gate trace seed

run:
	python -m careerpilot.gateway.cli

dashboard:
	python -m careerpilot.gateway.dashboard.app

telegram:
	python -m careerpilot.gateway.telegram

voice:
	python -m careerpilot.gateway.voice

eval:
	pytest evals/deterministic

eval-judge:
	pytest evals/judge

gate:
	python -m careerpilot.ops.release_gate

seed:
	python scripts/demo_seed.py
