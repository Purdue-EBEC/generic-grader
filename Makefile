bump:
	uv run cz bump --changelog
	@echo "Version bumped, changelog updated, committed, and tagged."
	@echo "Review with 'git log -1' then run 'make publish'."

build:
	rm -rf dist/
	uv build

publish: build
	uv publish
	git push --follow-tags
