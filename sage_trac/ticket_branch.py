# -*- coding: utf-8 -*-

from genshi.builder import tag
from genshi.core import TEXT
from genshi.filters import Transformer

from trac.core import *
from trac.config import Option
from trac.web.api import ITemplateStreamFilter
from trac.web.chrome import add_stylesheet, ITemplateProvider

from .common import GitBase, _signature_re

from . import git_merger

import pkg_resources
import pygit2

FILTER = Transformer('//td[@headers="h_branch"]')
FILTER_TEXT = Transformer('//td[@headers="h_branch"]/text()')


class TicketBranch(git_merger.GitMerger):
    """
    A Sage specific plugin which formats the ``branch`` field of a ticket and
    applies changes to the ``branch`` field to the git repository.
    """
    implements(ITemplateStreamFilter, ITemplateProvider)

    release_manager_signature = Option(
            'sage_trac', 'release_manager_signature',
            'Release Manager <release@sagemath.org>',
            doc='signature to use on commits (especially merges) made '
                'through action of the project release manager (default: '
                '"Release Manager <release@sagemath.org>)')

    def __init__(self):
        super(TicketBranch, self).__init__()

        m = _signature_re.match(self.release_manager_signature)
        if not m:
            raise TracError(
                '[sage_trac]/release_manager_signature in trac.ini must be '
                'in the "Name <email@example.com>" format')

        self._release_signature = pygit2.Signature(m.group(1), m.group(2))

    def filter_stream(self, req, method, filename, stream, data):
        """
        Reformat the ``branch`` field of a ticket to show the history of the
        linked branch.
        """
        branch = data.get('ticket', {'branch': None})['branch']
        if filename != 'ticket.html' or not branch:
            return stream

        def merge_link(url=None, class_='positive_review'):
            if url is None:
                return FILTER.attr("class", class_)

            return FILTER_TEXT.map(unicode.strip, TEXT).wrap(
                    tag.a(class_=class_, href=url))

        def commits_link(url):
            return FILTER.append(tag.span(' ')).\
                    append(tag.a('(Commits)', href=url))

        def error_filters(error):
            return (FILTER.attr("class", "needs_work"),
                    FILTER.attr("title", error))

        def apply_filters(filters):
            s = stream
            for filter in filters:
                s |= filter
            return s

        def error(error, filters=()):
            filters = tuple(filters)+error_filters(error)
            return apply_filters(filters)

        add_stylesheet(req, 'sage_trac/sage-ticket.css')

        branch = branch.strip()

        filters = []

        try:
            is_sha, branch = self.generic_lookup(branch)
            if is_sha:
                filters.append(
                        FILTER_TEXT.replace(branch.hex[:7]+' '))
        except (KeyError, ValueError) as err:
            if err.message.find('Ambiguous') < 0:
                return error("branch does not exist")
            else:
                return error("sha1 hash is too ambiguous")

        ret = self.get_merge(branch)
        merge_url, log_url = self.get_merge_url(req, branch, ret)

        if ret == git_merger.GIT_UPTODATE:
            if log_url is not None:
                filters.append(commits_link(self.log_url(base, branch)))

            if merge_url is None:
                filters.append(merge_link())
            else:
                filters.append(merge_link(merge_url))

            filters.append(
                    FILTER.attr("title", "already merged"))
        else:
            filters.append(commits_link(log_url))

            if ret == git_merger.GIT_FAILED_MERGE:
                return error("trac's automerging failed", filters)
            elif ret == git_merger.GIT_FASTFORWARD:
                filters.append(merge_link(merge_url))
            elif ret is not None:
                filters.append(merge_link(merge_url))
                filters.append(
                        FILTER.attr("title", "merges cleanly"))
            else:
                filters.append(merge_link(merge_url, 'needs_review'))

        return apply_filters(filters)

    # ITemplateProvider methods
    def get_templates_dirs(self):
        return []

    def get_htdocs_dirs(self):
        return [('sage_trac',
                 pkg_resources.resource_filename('sage_trac', 'htdocs'))]
