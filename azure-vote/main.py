from flask import Flask, request, render_template
import os
import random
import redis
import socket
import sys
import logging
import threading
from datetime import datetime

# App Insights
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from applicationinsights.flask.ext import AppInsights
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.metrics_exporter import MetricsExporter
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.tracer import Tracer
from opencensus.trace.samplers import ProbabilitySampler
app = Flask(__name__)

# Load configurations FIRST
app.config.from_pyfile('config_file.cfg')
instrumentation_key = os.environ.get('APPINSIGHTS_INSTRUMENTATIONKEY', app.config.get('APPINSIGHTS_INSTRUMENTATIONKEY'))
button1 = os.environ.get('VOTE1VALUE', app.config.get('VOTE1VALUE'))
button2 = os.environ.get('VOTE2VALUE', app.config.get('VOTE2VALUE'))
title = os.environ.get('TITLE', app.config.get('TITLE'))
show_host = os.environ.get('SHOWHOST', app.config.get('SHOWHOST'))
APPLICATIONINSIGHTS_CONNECTION_STRING = os.environ.get('APPLICATIONINSIGHTS_CONNECTION_STRING', app.config.get('APPLICATIONINSIGHTS_CONNECTION_STRING'))

# Standardize Connection String
conn_str = f'InstrumentationKey={instrumentation_key}'

# Requests
# middleware = AppInsights(app)
FlaskMiddleware(
    app,
    exporter=AzureExporter(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING),
    sampler=ProbabilitySampler(1.0)
)

# Logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
log_handler = AzureLogHandler(connection_string=conn_str)
log_handler.lock = threading.Lock()  
logger.addHandler(log_handler)

# Metrics
exporter = MetricsExporter(connection_string=f'InstrumentationKey={instrumentation_key}')

# Tracing
tracer = Tracer(
    exporter=AzureExporter(connection_string=f'InstrumentationKey={instrumentation_key}'),
    sampler=ProbabilitySampler(1.0)
)

# Redis Connection
r = redis.Redis()

# Change title to host name to demo NLB
if app.config['SHOWHOST'] == "true":
    title = socket.gethostname()

# Init Redis
if not r.get(button1): r.set(button1,0)
if not r.get(button2): r.set(button2,0)

@app.route('/', methods=['GET', 'POST'])
def index():

    if request.method == 'GET':

        # Get current values
        vote1 = r.get(button1).decode('utf-8')
        with tracer.span(name="cat_vote_read"):
            pass

        vote2 = r.get(button2).decode('utf-8')
        with tracer.span(name="dog_vote_read"):
            pass

        # Return index with values
        return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

    elif request.method == 'POST':

        if request.form['vote'] == 'reset':

            # Empty table and return results
            r.set(button1,0)
            r.set(button2,0)

            vote1 = r.get(button1).decode('utf-8')
            properties = {'custom_dimensions': {'Cats Vote': vote1}}
            logger.info("Cat votes reset", extra=properties)

            vote2 = r.get(button2).decode('utf-8')
            properties = {'custom_dimensions': {'Dogs Vote': vote2}}
            logger.info("Dog votes reset", extra=properties)

            return render_template("index.html", value1=0, value2=0, button1=button1, button2=button2, title=title)

        else:

            # Insert vote result into DB
            vote = request.form['vote']
            r.incr(vote,1)

            # Get current values
            vote1 = r.get(button1).decode('utf-8')
            vote2 = r.get(button2).decode('utf-8')

            # Return results
            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)

