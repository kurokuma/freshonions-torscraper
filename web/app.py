from flask import Flask
from flask import request
from flask import render_template
from flask import jsonify
from flask import url_for
from flask import redirect
from flask import send_from_directory
import urlparse
from pony.orm import *
from datetime import *
from tor_db import *
import re
import os
app = Flask(__name__)
app.jinja_env.globals.update(Domain=Domain)
app.jinja_env.globals.update(NEVER=NEVER)
@app.context_processor
@db_session
def inject_counts():
	event_horizon = datetime.now() - timedelta(days=1)
	domain_count = count(d for d in Domain if d.is_up == True and d.is_crap == False)
	day_count    = count(d for d in Domain if d.is_up == True and d.is_crap == False and d.created_at > event_horizon)
	return dict(day_count=day_count, domain_count=domain_count)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html',code=404,message="Page not found."), 404


@app.route("/")
@db_session
def index():
	now = datetime.now()
	event_horizon = now - timedelta(days=30)
	domains = []
	show_all = request.args.get("show", "") == "all"
	if not show_all:
		domains = Domain.select(lambda p: p.last_alive > event_horizon and p.is_crap == False).order_by(desc(Domain.created_at))
	else:
		domains = Domain.select(lambda p: p.last_alive > event_horizon).order_by(desc(Domain.created_at))

	return render_template('index.html', domains=domains, Domain=Domain)

@app.route('/json')
@db_session
def json():
	now = datetime.now()
	event_horizon = now - timedelta(days=30)
	domains = Domain.select(lambda p: p.last_alive > event_horizon).order_by(desc(Domain.created_at))
	out = []
	for domain in domains:
		d = dict()
		d['url']        = domain.index_url()
		d['title']      = domain.title
		d['is_up']      = domain.is_up
		d['created_at'] = domain.created_at
		d['visited_at'] = domain.visited_at
		d['last_seen']  = domain.last_alive
		d['is_genuine'] = domain.is_genuine
		d['is_fake']    = domain.is_fake
		out.append(d)

	return jsonify(out)

@app.route('/src')
def src():
	current = os.path.dirname(os.path.realpath(__file__))
	version_file = current+"/../etc/version_string"
	with open(version_file,'r') as f:
		version_string = f.read().strip()

	source_name="torscraper-%s.tar.gz" % version_string
	source_link="/static/%s" % source_name
	return render_template('src.html', source_name=source_name, source_link=source_link)

@app.route('/info', methods=['GET', 'POST'])
def info():
	if request.method == 'POST':
		onion = request.form['onion'].strip()
		if not onion:
			return render_template('error.html', code=500, message="WHY U NO ONION?"), 500
		if re.match('^(http://|https://)', onion):
			try:
				parsed = urlparse.urlparse(onion)
				onion = parsed.hostname
			except:
				onion = onion
		if not re.match('.*\.onion$', onion):
			onion = onion + ".onion"
		return redirect(url_for("onion_info",onion=onion), code=302)
	return render_template("info.html")


@app.route('/info/<onion>')
@db_session
def onion_info(onion):
	links_to = []
	links_from = []
	domain = select(d for d in Domain if d.host==onion).first()
	if domain:
		links_to   = domain.links_to()
		links_from = domain.links_from()
		return render_template('onion_info.html', domain=domain, links_to=links_to, links_from = links_from)
	else:
		return render_template('error.html', code=404, message="Onion not found."), 404


@app.route('/info/<onion>/json')
@db_session
def onion_info_json(onion):
	links_to = []
	links_from = []
	domain = select(d for d in Domain if d.host==onion).first()
	if not domain:
		return render_template('error.html', code=404, message="Onion not found."), 404

	links_to   = domain.links_to()
	links_from = domain.links_from()
	d = dict()
	d['url']        = domain.index_url()
	d['title']      = domain.title
	d['is_up']      = domain.is_up
	d['created_at'] = domain.created_at
	d['visited_at'] = domain.visited_at
	d['last_seen']  = domain.last_alive
	d['is_genuine'] = domain.is_genuine
	d['is_fake']    = domain.is_fake
	d['links_to']   = []
	d['links_from'] = []

	for link_to in links_to:
		d['links_to'].append(link_to.index_url())
	for link_from in links_from:
		d['links_from'].append(link_from.index_url())

	return jsonify(d)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/faq')
def faq():
	return render_template('faq.html')


if __name__ == "__main__":
    app.run(host="0.0.0.0")