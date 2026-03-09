# Extract current version from pyproject.toml
VERSION=$(shell grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
MAJOR=$(shell echo $(VERSION) | cut -d. -f1)
MINOR=$(shell echo $(VERSION) | cut -d. -f2)
PATCH=$(shell echo $(VERSION) | cut -d. -f3)
NEXT_PATCH=$(shell echo $$(($(PATCH) + 1)))
NEXT_VERSION=$(MAJOR).$(MINOR).$(NEXT_PATCH)

bump:
	@echo "Bumping version: $(VERSION) -> $(NEXT_VERSION)"
	sed -i 's/^version = "$(VERSION)"/version = "$(NEXT_VERSION)"/' pyproject.toml
	uv sync
	git add pyproject.toml uv.lock
	git commit -m "Bump version to $(NEXT_VERSION)"
	git tag -a v$(NEXT_VERSION) -m "Release v$(NEXT_VERSION)"
	@echo "Version bumped, committed, and tagged v$(NEXT_VERSION)."
	@echo "Review with 'git log -1' then run 'make publish'."

build:
	uv build

publish: build
	uv publish
