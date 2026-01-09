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
from applicationinsights import TelemetryClient
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.metrics_exporter import MetricsExporter
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.tracer import Tracer
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.stats import stats as stats_module
from opencensus.stats import measure as measure_module
from opencensus.stats import view as view_module
from opencensus.stats import aggregation as aggregation_module

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
conn_str = APPLICATIONINSIGHTS_CONNECTION_STRING

# Requests
# middleware = AppInsights(app)
FlaskMiddleware(
    app,
    exporter=AzureExporter(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING),
    sampler=ProbabilitySampler(1.0)
)

tc = TelemetryClient(instrumentation_key)

# Logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
log_handler = AzureLogHandler(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING)
log_handler.lock = threading.Lock()  
logger.addHandler(log_handler)

# Metrics
exporter = MetricsExporter(connection_string=f'InstrumentationKey={instrumentation_key}')

# Tracing
tracer = Tracer(
    exporter=AzureExporter(connection_string=f'InstrumentationKey={instrumentation_key}'),
    sampler=ProbabilitySampler(1.0)
)

stats = stats_module.stats
view_manager = stats.view_manager
stats_recorder = stats.stats_recorder

vote_measure = measure_module.MeasureInt(
    "votes_count",
    "Number of votes",
    "votes"
)

vote_view = view_module.View(
    "votes_count_view",
    "Votes count",
    [],
    vote_measure,
    aggregation_module.CountAggregation()
)

view_manager.register_view(vote_view)

# Redis Connection
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

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
        vote1 = r.get(button1)
        with tracer.span(name="cat_vote_read") as span:
            span.add_attribute("vote.type", "Cats")
            span.add_attribute("vote.count", vote1)


        vote2 = r.get(button2)
        with tracer.span(name="dog_vote_read") as span:
            span.add_attribute("vote.type", "Dogs")
            span.add_attribute("vote.count", vote2)


        # Return index with values
        return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

    elif request.method == 'POST':

        if request.form['vote'] == 'reset':

            # Empty table and return results
            r.set(button1,0)
            r.set(button2,0)

            vote1 = r.get(button1)
            properties = {'custom_dimensions': {'Cats Vote': vote1}}
            logger.info("Cat votes reset", extra=properties)

            vote2 = r.get(button2)
            properties = {'custom_dimensions': {'Dogs Vote': vote2}}
            logger.info("Dog votes reset", extra=properties)

            return render_template("index.html", value1=0, value2=0, button1=button1, button2=button2, title=title)

        else:

            # Insert vote result into DB
            vote = request.form['vote']
            r.incr(vote,1)

            mmap = stats_recorder.new_measurement_map()
            mmap.measure_int_put(vote_measure, 1)
            mmap.record()

            with tracer.span(name="vote_event") as span:
                span.add_attribute("vote.choice", vote)
                span.add_attribute("event.time", str(datetime.utcnow()))


            if vote == button1:
                tc.track_event(
                    "VoteSubmitted",
                    {"Animal": "Cats"}
                )
                logger.info("Cats vote submitted")

            elif vote == button2:
                tc.track_event(
                    "VoteSubmitted",
                    {"Animal": "Dogs"}
                )
                logger.info("Dogs vote submitted")

            tc.flush()

            # Get current values
            vote1 = r.get(button1)
            vote2 = r.get(button2)
            
            # Return results
            return render_template("index.html", value1=int(vote1), value2=int(vote2), button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)

