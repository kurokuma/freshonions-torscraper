import os
from datetime import *
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import DocType, Date, Nested, Boolean, MetaField
from elasticsearch_dsl import analyzer, InnerObjectWrapper, Text, Integer
from elasticsearch import serializer, compat, exceptions
from elasticsearch_dsl import Search
from elasticsearch_dsl import Q
from elasticsearch_dsl import Index
import re
try:
    import simplejson as json
except ImportError:
    import json

class JSONSerializerPython2(serializer.JSONSerializer):
    """Override elasticsearch library serializer to ensure it encodes utf characters during json dump.
    See original at: https://github.com/elastic/elasticsearch-py/blob/master/elasticsearch/serializer.py#L42
    A description of how ensure_ascii encodes unicode characters to ensure they can be sent across the wire
    as ascii can be found here: https://docs.python.org/2/library/json.html#basic-usage
    """
    def dumps(self, data):
        # don't serialize strings
        if isinstance(data, compat.string_types):
            return data
        try:
            return json.dumps(data, default=self.default, ensure_ascii=True)
        except (ValueError, TypeError) as e:
            raise exceptions.SerializationError(data, e)

def elasticsearch_pages(context, sort):
    NEVER = datetime.fromtimestamp(0)
    domain_query = Q("range",created_at={'gt':NEVER})
    if context["is_up"]:
        domain_query = domain_query & Q("match", is_up=True)
    if not context["show_fh_default"]:
        domain_query = domain_query & Q("match", is_crap=False)
    if not context["show_subdomains"]:
        domain_query = domain_query & Q("match", is_subdomain=False)
    if context["rep"] == "genuine":
        domain_query = domain_query & Q("match", is_genuine=True)
    if context["rep"] == "fake":
        domain_query = domain_query & Q("match", is_fake=True)

    limit = 20000 if context["more"] else 1000

    has_parent_query = Q("has_parent", type="domain", query=domain_query)
    query = Search().query(has_parent_query & Q("match", body_stripped=context['search'])).highlight_options(order='score', encoder='html').highlight('body_stripped')[:limit]
    return query.execute()


def is_elasticsearch_enabled():
    return ('ELASTICSEARCH_ENABLED' in os.environ and os.environ['ELASTICSEARCH_ENABLED'].lower()=='true')

class DomainDocType(DocType):
    title = Text(analyzer="snowball")
    created_at = Date()
    visited_at = Date()
    last_alive = Date()
    is_up      = Boolean()
    is_fake    = Boolean()
    is_genuine = Boolean()
    is_crap    = Boolean()
    url        = Text()
    is_subdomain = Boolean()
    ssl        = Boolean()
    port       = Integer()

    class Meta:
        name = 'domain'
        doc_type = 'domain'

    @classmethod
    def get_indexable(cls):
        return cls.get_model().get_objects()

    @classmethod
    def from_obj(klass, obj):
        return klass(
            meta={'id': obj.host},
            title=obj.title,
            created_at=obj.created_at,
            visited_at=obj.visited_at,
            is_up=obj.is_up,
            is_fake=obj.is_fake,
            is_genuine=obj.is_fake,
            is_crap=obj.is_crap,
            url=obj.index_url(),
            is_subdomain=obj.is_subdomain,
            ssl=obj.ssl,
            port=obj.port
        )

    @classmethod
    def set_isup(klass, obj, is_up):
    	dom = klass(meta={'id': obj.host})
    	dom.update(is_up=is_up)


class PageDocType(DocType):
    html_strip = analyzer('html_strip', 
        tokenizer="standard",
        filter=["standard", "lowercase", "stop", "snowball"],
        char_filter=["html_strip"]
    )

    title = Text(analyzer="snowball")
    created_at   =  Date()
    visited_at    = Date()
    code          = Integer()
    body          = Text()
    body_stripped = Text(analyzer=html_strip)
    is_frontpage  = Boolean()
    nid           = Integer()

    class Meta:
        name = 'page'
        doc_type = 'page'
        parent = MetaField(type='domain')

    @classmethod
    def get_indexable(cls):
        return cls.get_model().get_objects()

    @classmethod
    def from_obj(klass, obj, body):
        return klass(
            meta={'id':obj.url, 'routing':obj.domain.host, 'parent':obj.domain.host},
            title=obj.title,
            created_at=obj.created_at,
            visited_at=obj.visited_at,
            is_frontpage=obj.is_frontpage,
            code=obj.code,
            body=body,
            body_stripped=re.sub('<[^<]+?>', '', body),
            nid=obj.id
        )

hidden_services = None

if is_elasticsearch_enabled():
    connections.create_connection(hosts=[os.environ['ELASTICSEARCH_HOST']], serializer=JSONSerializerPython2(), timeout=20)
    hidden_services = Index('hiddenservices')
    hidden_services.doc_type(DomainDocType)
    hidden_services.doc_type(PageDocType)

def migrate():
    hidden_services = Index('hiddenservices')
    hidden_services.delete(ignore=404)
    hidden_services = Index('hiddenservices')
    hidden_services.doc_type(DomainDocType)
    hidden_services.doc_type(PageDocType)
    hidden_services.create()
