## Contributing to MultiCamEditor

Thank you for your interest in contributing!  The project welcomes
improvements and bug fixes.  Please follow these guidelines to ensure a
smooth development experience.

### Getting Set Up

1. **Fork the repository** on GitHub and clone your fork locally.
2. **Create a virtual environment** for development:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Install optional runtime dependencies** (e.g. PyQt6) if you plan to
   run the GUI.  These are not included in `requirements.txt`.

### Development Workflow

* Create a new branch for your work off of `main`.
* Write code using **type hints** and follow the existing project structure.
* Run `ruff` and `black` to lint and format your changes:

  ```bash
  ruff check --fix .
  black .
  ```

* Add or update **tests** under the `tests/` directory to cover your
  changes.  Aim for high coverage and consider edge cases.
* Run `pytest -q` to ensure the tests pass.
* Run `mypy .` to type‑check your changes.
* Commit using clear, descriptive messages.  Follow conventional commit
  semantics where possible (e.g. `fix:`, `feat:`, `docs:`).

### Submitting Changes

When you are ready, push your branch to your fork and open a pull
request against the upstream repository.  Include a description of the
problem being solved and how your solution addresses it.  The CI
pipeline will run automatically on your pull request.  Please make sure
it passes before requesting review.

### Code of Conduct

Be respectful and considerate in all interactions.  We appreciate your
time and contributions.