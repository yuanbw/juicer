from __future__ import print_function
from six import reraise as raise_
import sys

from jinja2 import nodes
from jinja2.ext import Extension
from juicer.exceptions import JuicerException


class HandleExceptionExtension(Extension):
    # a set of names that trigger the extension.
    tags = {'handleinstance'}

    def __init__(self, environment):
        super(HandleExceptionExtension, self).__init__(environment)
        environment.extend()

    def parse(self, parser):
        lineno = parser.stream.next().lineno

        # Retrieves instance
        args = [parser.parse_expression()]
        body = parser.parse_statements(['name:endhandleinstance'],
                                       drop_needle=True)

        result = nodes.CallBlock(self.call_method('_handle', args),
                                 [], [], body).set_lineno(lineno)
        return result

    def _handle(self, instance, caller):
        try:
            return caller()
        except KeyError:
            msg = ('Key error parsing template for instance {instance}. '
                   'Probably there is a problem with port specification')\
                .format(instance=instance.__class__.__name__)
            raise_(JuicerException(msg), None, sys.exc_info()[2])
        except TypeError:
            msg = 'Type error parsing template for instance ' \
                  '{instance}.'.format(instance=instance.__class__.__name__)
            raise_(JuicerException(msg), None, sys.exc_info()[2])