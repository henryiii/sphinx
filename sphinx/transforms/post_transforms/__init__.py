# -*- coding: utf-8 -*-
"""
    sphinx.transforms.post_transforms
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Docutils transforms used by Sphinx.

    :copyright: Copyright 2007-2018 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from docutils import nodes

from sphinx import addnodes
from sphinx.environment import NoUri
from sphinx.locale import __
from sphinx.transforms import SphinxTransform
from sphinx.util import logging
from sphinx.util.nodes import process_only_nodes

if False:
    # For type annotation
    from typing import Any, Dict, List, Tuple  # NOQA
    from sphinx.application import Sphinx  # NOQA
    from sphinx.domains import Domain  # NOQA


logger = logging.getLogger(__name__)


class ReferencesResolver(SphinxTransform):
    """
    Resolves cross-references on doctrees.
    """

    default_priority = 10

    def apply(self, **kwargs):
        # type: (Any) -> None
        for node in self.document.traverse(addnodes.pending_xref):
            contnode = node[0].deepcopy()
            newnode = None

            typ = node['reftype']
            target = node['reftarget']
            refdoc = node.get('refdoc', self.env.docname)
            domain = None

            try:
                if 'refdomain' in node and node['refdomain']:
                    # let the domain try to resolve the reference
                    try:
                        domain = self.env.domains[node['refdomain']]
                    except KeyError:
                        raise NoUri
                    newnode = domain.resolve_xref(self.env, refdoc, self.app.builder,
                                                  typ, target, node, contnode)
                # really hardwired reference types
                elif typ == 'any':
                    newnode = self.resolve_anyref(refdoc, node, contnode)
                # no new node found? try the missing-reference event
                if newnode is None:
                    newnode = self.app.emit_firstresult('missing-reference', self.env,
                                                        node, contnode)
                    # still not found? warn if node wishes to be warned about or
                    # we are in nit-picky mode
                    if newnode is None:
                        self.warn_missing_reference(refdoc, typ, target, node, domain)
            except NoUri:
                newnode = contnode
            node.replace_self(newnode or contnode)

    def resolve_anyref(self, refdoc, node, contnode):
        # type: (unicode, nodes.Node, nodes.Node) -> nodes.Node
        """Resolve reference generated by the "any" role."""
        stddomain = self.env.get_domain('std')
        target = node['reftarget']
        results = []  # type: List[Tuple[unicode, nodes.Node]]
        # first, try resolving as :doc:
        doc_ref = stddomain.resolve_xref(self.env, refdoc, self.app.builder,
                                         'doc', target, node, contnode)
        if doc_ref:
            results.append(('doc', doc_ref))
        # next, do the standard domain (makes this a priority)
        results.extend(stddomain.resolve_any_xref(self.env, refdoc, self.app.builder,
                                                  target, node, contnode))
        for domain in self.env.domains.values():
            if domain.name == 'std':
                continue  # we did this one already
            try:
                results.extend(domain.resolve_any_xref(self.env, refdoc, self.app.builder,
                                                       target, node, contnode))
            except NotImplementedError:
                # the domain doesn't yet support the new interface
                # we have to manually collect possible references (SLOW)
                for role in domain.roles:
                    res = domain.resolve_xref(self.env, refdoc, self.app.builder,
                                              role, target, node, contnode)
                    if res and isinstance(res[0], nodes.Element):
                        results.append(('%s:%s' % (domain.name, role), res))
        # now, see how many matches we got...
        if not results:
            return None
        if len(results) > 1:
            def stringify(name, node):
                reftitle = node.get('reftitle', node.astext())
                return ':%s:`%s`' % (name, reftitle)
            candidates = ' or '.join(stringify(name, role) for name, role in results)
            logger.warning(__('more than one target found for \'any\' cross-'
                              'reference %r: could be %s'), target, candidates,
                           location=node)
        res_role, newnode = results[0]
        # Override "any" class with the actual role type to get the styling
        # approximately correct.
        res_domain = res_role.split(':')[0]
        if newnode and newnode[0].get('classes'):
            newnode[0]['classes'].append(res_domain)
            newnode[0]['classes'].append(res_role.replace(':', '-'))
        return newnode

    def warn_missing_reference(self, refdoc, typ, target, node, domain):
        # type: (unicode, unicode, unicode, nodes.Node, Domain) -> None
        warn = node.get('refwarn')
        if self.config.nitpicky:
            warn = True
            if self.config.nitpick_ignore:
                dtype = domain and '%s:%s' % (domain.name, typ) or typ
                if (dtype, target) in self.config.nitpick_ignore:
                    warn = False
                # for "std" types also try without domain name
                if (not domain or domain.name == 'std') and \
                   (typ, target) in self.config.nitpick_ignore:
                    warn = False
        if not warn:
            return
        if domain and typ in domain.dangling_warnings:
            msg = domain.dangling_warnings[typ]
        elif node.get('refdomain', 'std') not in ('', 'std'):
            msg = (__('%s:%s reference target not found: %%(target)s') %
                   (node['refdomain'], typ))
        else:
            msg = __('%r reference target not found: %%(target)s') % typ
        logger.warning(msg % {'target': target},
                       location=node, type='ref', subtype=typ)


class OnlyNodeTransform(SphinxTransform):
    default_priority = 50

    def apply(self, **kwargs):
        # type: (Any) -> None
        # A comment on the comment() nodes being inserted: replacing by [] would
        # result in a "Losing ids" exception if there is a target node before
        # the only node, so we make sure docutils can transfer the id to
        # something, even if it's just a comment and will lose the id anyway...
        process_only_nodes(self.document, self.app.builder.tags)


def setup(app):
    # type: (Sphinx) -> Dict[unicode, Any]
    app.add_post_transform(ReferencesResolver)
    app.add_post_transform(OnlyNodeTransform)

    return {
        'version': 'builtin',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
