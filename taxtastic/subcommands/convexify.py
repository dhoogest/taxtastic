"""Finds discordance in a reference package"""

from Bio import Phylo
from Bio.Phylo.PhyloXML import BranchColor

from StringIO import StringIO
import collections
import itertools
import argparse
import operator
import copy

from taxtastic import algotax, refpkg

import logging
log = logging.getLogger(__name__)

def build_parser(parser):
    parser.add_argument('refpkg', nargs=1,
        help='the reference package to operate on')
    parser.add_argument('-d', '--discordance', metavar='FILE',
        type=argparse.FileType('wb'),
        help='write a phyloxml discordance tree to the provided path')
    parser.add_argument('-t', '--tax-tree', metavar='FILE',
        type=argparse.FileType('rb'),
        help='use a tree as provided by `guppy ref_tree`')
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument('-s', '--summary',
        action='store_const', dest='verbosity', const=1, default=2,
        help='show only a summary instead of the full output')
    verbosity.add_argument('-q', '--quiet',
        action='store_const', dest='verbosity', const=0,
        help='produce no output')

def action(args):
    log.info('loading reference package')
    rp = refpkg.Refpkg(args.refpkg[0])

    if args.tax_tree:
        tree = next(Phylo.parse(args.tax_tree, 'phyloxml'))
    else:
        with rp.resource('tree_file', 'rU') as fobj:
            tree = Phylo.read(fobj, 'newick')
        tree = tree.as_phyloxml()

    rp.load_db()
    curs = rp.db.cursor()
    seq_colors = curs.execute("""
        SELECT t.rank,
               seqname,
               t.tax_name
        FROM   parents
               JOIN taxa t
                 ON t.tax_id = parent
               JOIN sequences s
                 ON s.tax_id = child
    """)
    rank_map = collections.defaultdict(list)
    for rank, seq, color in seq_colors:
        rank_map[rank].append((seq, color))

    rank_order = curs.execute("""
        SELECT   rank
        FROM     ranks
        ORDER BY rank_order ASC
    """)

    discordance_trees = []
    discordance_tree = None
    for rank, in rank_order:
        seq_colors = rank_map[rank]
        if not seq_colors:
            continue
        clade_map = {c.name: c for c in tree.get_terminals()}
        colors = {clade_map[seq]: color for seq, color in seq_colors}
        log.warn('calculating for %s (|coloring| is %d)', rank, len(colors))
        metadata = algotax.color_clades(tree, colors)
        badness = [len(cut) - 1
            for node, cut in metadata.cut_colors.iteritems()
            if node != tree.root and len(cut) > 1]
        max_badness = max(badness) if badness else 0
        tot_badness = sum(badness)
        if not max_badness:
            log.info('  completely convex; skipping')
            continue

        log.info('  badness: %d max, %d tot', max_badness, tot_badness)
        result = algotax.walk(tree.root, metadata)
        log.info('  discordance: %d', len(clade_map) - len(result))
        if args.discordance:
            # XXX find a better method of doing this
            discordance_tree = copy.deepcopy(tree)
            discordance_tree.name = rank

        cut_nodes = set(tree.get_terminals()) - result
        for node in sorted(cut_nodes, key=operator.attrgetter('name')):
            log.debug('    %s', node.name)

            if not discordance_tree:
                continue
            node = discordance_tree.find_any(name=node.name)
            node.color = BranchColor(255, 0, 0)
            node.width = 5

        if not discordance_tree:
            continue
        discordance_trees.append(discordance_tree)

    if args.discordance:
        log.info('writing out discordance tree')
        Phylo.write(discordance_trees, args.discordance, 'phyloxml')