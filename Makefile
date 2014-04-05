.PHONY: deps server client clean

deps:
	@command -v virtualenv >/dev/null 2>&1 || { echo >&2 "nimbus requires virtualenv, but it's not installed: aborting."; exit 1; }
	virtualenv venv
	. venv/bin/activate; ARCHFLAGS=-Wno-error=unused-command-line-argument-hard-error-in-future pip install -r conf/requirements.txt
	. venv/bin/activate; install_name_tool -change libmysqlclient.18.dylib /usr/local/mysql/lib/libmysqlclient.18.dylib venv/lib/python2.7/site-packages/_mysql.so

server:
	. venv/bin/activate; python server.py $(ARGS)

client:
	. venv/bin/activate; python client.py $(ARGS)

clean:
	rm -rf venv
