# c-sharp-user-image

This image inherits the [base-python-image](https://github.com/cal-icor/base-python-image) and extends it to add C# Jupyter kernels and VSCode extensions.

See this repository's [CONTRIBUTING.md](https://github.com/cal-icor/c-sharp-user-image/blob/main/CONTRIBUTING.md) for instructions.

## Building the image locally

You should use [jupyter-repo2-docker](https://repo2docker.readthedocs.io/en/latest/) to build and use/test the image on your own device before you push and create a PR.  It's better (and typically faster) to do this first before using CI/CD.  There's no need to waste Github Action minutes to test build images when you can do this on your own device!

Run `repo2docker` from inside the cloned image repo.  To run on a linux/WSL2 linux shell:

``` bash
repo2docker . # <--- the path to the repo
```

If you are using an ARM CPU (Apple M* silicon), you will need to run `jupyter-repo2docker` with the following arguments:

``` bash
jupyter-repo2docker --user-id=1000 --user-name=jovyan \
  --Repo2Docker.platform=linux/amd64 \
  --target-repo-dir=/home/jovyan/.cache \
  -e PLAYWRIGHT_BROWSERS_PATH=/srv/conda \
  . # <--- the path to the repo
```

If you just want to see if the image builds, but not automatically launch the server, add `--no-run` to the arguments (before the final `.`).

## Running the browser tests locally

Once you've built the image, you can run the same browser tests CI runs. Despite the name, these tests don't drive a browser UI; they start the built image as a JupyterLab server and talk to its kernel REST and WebSocket API directly. The container has to be serving on port 8888 with an empty token, which is what CI does.

First, build the image with a name you can reference (the plain `repo2docker .` form above autogenerates one):

``` bash
jupyter-repo2docker --no-run --image-name c-sharp-user-image:local .
```

Start the image as a container serving JupyterLab on port 8888 with no token:

``` bash
docker run -d --name browser-test-container -p 8888:8888 \
  c-sharp-user-image:local \
  jupyter lab --ip=0.0.0.0 --no-browser --ServerApp.token=''
```

Wait for the server to be ready:

``` bash
curl --retry 30 --retry-delay 3 --retry-connrefused -sf http://localhost:8888/api/status
```

Install the test dependencies and Playwright's chromium, then run the tests:

``` bash
pip install -r browser-tests/requirements.txt
playwright install chromium
pytest browser-tests/ -v
```

When you're done, stop and remove the container:

``` bash
docker stop browser-test-container && docker rm browser-test-container
```
