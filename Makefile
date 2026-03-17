IMAGE := youtube-to-pdf:local
MAKE_STATE_DIR := .make
URL_VALUE_FILE := $(MAKE_STATE_DIR)/url.txt
FILE_VALUE_FILE := $(MAKE_STATE_DIR)/batch_path.txt

.PHONY: doctor build run batch test clean

doctor:
	@python3 scripts/docker_runner.py doctor

build:
	@python3 scripts/docker_runner.py build

run:
	@if [ -z "$(strip $(value URL))" ]; then echo "Usage: make run URL='<youtube-url>'" >&2; exit 1; fi
	@mkdir -p $(MAKE_STATE_DIR)
	@$(file >$(URL_VALUE_FILE),$(value URL))
	@python3 scripts/docker_runner.py run --value-file $(URL_VALUE_FILE)

batch:
	@if [ -z "$(strip $(value FILE))" ]; then echo "Usage: make batch FILE='/absolute/or/relative/urls.txt'" >&2; exit 1; fi
	@mkdir -p $(MAKE_STATE_DIR)
	@$(file >$(FILE_VALUE_FILE),$(value FILE))
	@python3 scripts/docker_runner.py batch --value-file $(FILE_VALUE_FILE)

test: build
	@python3 scripts/docker_runner.py test

clean:
	@rm -rf $(MAKE_STATE_DIR) .pytest_cache
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +

