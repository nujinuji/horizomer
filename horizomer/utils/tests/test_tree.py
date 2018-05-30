#!/usr/bin/env python

# ----------------------------------------------------------------------------
# Copyright (c) 2015--, The Horizomer Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from unittest import TestCase, main
from shutil import rmtree
from tempfile import mkdtemp
from os.path import join, dirname, realpath
from skbio import TreeNode

from horizomer.utils.tree import (
    support, unpack, has_duplicates, compare_topology, intersect_trees,
    unpack_by_func, read_taxdump, build_taxdump_tree, order_nodes,
    is_ordered, cladistic, _compare_length, compare_branch_lengths,
    assign_supports, walk_copy, root_above, _exact_compare, root_by_outgroup)


class TreeTests(TestCase):

    def setUp(self):
        """ Set up working directory and test files
        """
        # test output can be written to this directory
        self.working_dir = mkdtemp()

        # test data directory
        datadir = join(dirname(realpath(__file__)), 'data')

        # test data files
        self.nodes_fp = join(datadir, 'nodes.dmp')
        self.names_fp = join(datadir, 'names.dmp')

    def tearDown(self):
        # there isn't any file to remove at the moment
        # but in the future there will be
        rmtree(self.working_dir)

    def test_support(self):
        """Test getting support value of a node."""
        # test nodes with support alone as label
        tree = TreeNode.read(['((a,b)75,(c,d)90);'])
        node1, node2 = tree.children
        self.assertEqual(support(node1), 75.0)
        self.assertEqual(support(node2), 90.0)

        # test nodes with support and branch length
        tree = TreeNode.read(['((a,b)0.85:1.23,(c,d)0.95:4.56);'])
        node1, node2 = tree.children
        self.assertEqual(support(node1), 0.85)
        self.assertEqual(support(node2), 0.95)

        # test nodes with support and extra label (not a common scenario but
        # can happen)
        tree = TreeNode.read(['((a,b)\'80:X\',(c,d)\'60:Y\');'])
        node1, node2 = tree.children
        self.assertEqual(support(node1), 80.0)
        self.assertEqual(support(node2), 60.0)

        # test nodes without label, with non-numeric label, and with branch
        # length only
        tree = TreeNode.read(['((a,b),(c,d)x,(e,f):1.0);'])
        for node in tree.children:
            self.assertIsNone(support(node))

    def test_unpack(self):
        """Test unpacking an internal node."""
        # test unpacking a node without branch length
        tree = TreeNode.read(['((c,d)a,(e,f)b);'])
        unpack(tree.find('b'))
        exp = '((c,d)a,e,f);\n'
        self.assertEqual(str(tree), exp)

        # test unpacking a node with branch length
        tree = TreeNode.read(['((c:2.0,d:3.0)a:1.0,(e:2.0,f:1.0)b:2.0);'])
        unpack(tree.find('b'))
        exp = '((c:2.0,d:3.0)a:1.0,e:4.0,f:3.0);'
        self.assertEqual(str(tree).rstrip(), exp)

        # test attempting to unpack root
        tree = TreeNode.read(['((d,e)b,(f,g)c)a;'])
        msg = 'Cannot unpack root.'
        with self.assertRaisesRegex(ValueError, msg):
            unpack(tree.find('a'))

    def test_has_duplicates(self):
        """Test checking for duplicated taxa."""
        # test tree without duplicates
        tree = TreeNode.read(['((a,b),(c,d));'])
        obs = has_duplicates(tree)
        self.assertFalse(obs)

        # test tree with duplicates
        tree = TreeNode.read(['((a,a),(c,a));'])
        obs = has_duplicates(tree)
        self.assertTrue(obs)

        tree = TreeNode.read(['((1,(2,x)),4,(5,(6,x,8)));'])
        obs = has_duplicates(tree)
        self.assertTrue(obs)

        # test tree with empty taxon names (not a common scenario but can
        # happen)
        tree = TreeNode.read(['((1,(2,,)),4,(5,(6,,8)));'])
        msg = 'Empty taxon name\(s\) found.'
        with self.assertRaisesRegex(ValueError, msg):
            has_duplicates(tree)

    def test_compare_topology(self):
        """Test comparing topologies of two trees."""
        # test identical Newick strings
        tree1 = TreeNode.read(['(a,b)c;'])
        tree2 = TreeNode.read(['(a,b)c;'])
        obs = compare_topology(tree1, tree2)
        self.assertTrue(obs)

        # test identical topologies with different branch lengths
        tree1 = TreeNode.read(['(a:1,b:2)c:3;'])
        tree2 = TreeNode.read(['(a:3,b:2)c:1;'])
        obs = compare_topology(tree1, tree2)
        self.assertTrue(obs)

        # test identical topologies with flipped child nodes
        tree1 = TreeNode.read(['(a,b)c;'])
        tree2 = TreeNode.read(['(b,a)c;'])
        obs = compare_topology(tree1, tree2)
        self.assertTrue(obs)

        tree1 = TreeNode.read(['((4,5)2,(6,7,8)3)1;'])
        tree2 = TreeNode.read(['((8,7,6)3,(5,4)2)1;'])
        obs = compare_topology(tree1, tree2)
        self.assertTrue(obs)

        tree1 = TreeNode.read(['(((9,10)4,(11,12,13)5)2,((14)6,(15,16,17,18)7,'
                               '(19,20)8)3)1;'])
        tree2 = TreeNode.read(['(((15,16,17,18)7,(14)6,(20,19)8)3,((12,13,11)5'
                               ',(10,9)4)2)1;'])
        obs = compare_topology(tree1, tree2)
        self.assertTrue(obs)

        # test different topologies
        tree1 = TreeNode.read(['(a,b)c;'])
        tree2 = TreeNode.read(['(a,c)b;'])
        obs = compare_topology(tree1, tree2)
        self.assertFalse(obs)

        tree1 = TreeNode.read(['((4,5)2,(6,7,8)3)1;'])
        tree2 = TreeNode.read(['((4,5)3,(6,7,8)2)1;'])
        obs = compare_topology(tree1, tree2)
        self.assertFalse(obs)

        tree1 = TreeNode.read(['((4,5)2,(6,7,8)3)1;'])
        tree2 = TreeNode.read(['(((4,1)8)7,(6,3)2)5;'])
        obs = compare_topology(tree1, tree2)
        self.assertFalse(obs)

    def test_intersect_trees(self):
        """Test intersecting two trees."""
        # test trees with identical taxa
        tree1 = TreeNode.read(['((a,b),(c,d));'])
        tree2 = TreeNode.read(['(a,(b,c,d));'])
        obs = intersect_trees(tree1, tree2)
        exp = (tree1, tree2)
        for i in range(2):
            self.assertEqual(obs[i].compare_subsets(exp[i]), 0.0)

        # test trees with partially different taxa
        tree1 = TreeNode.read(['((a,b),(c,d));'])
        tree2 = TreeNode.read(['((a,b),(c,e));'])
        obs = intersect_trees(tree1, tree2)
        tree1_lap = TreeNode.read(['((a,b),c);'])
        tree2_lap = TreeNode.read(['((a,b),e);'])
        exp = (tree1_lap, tree2_lap)
        for i in range(2):
            self.assertEqual(obs[i].compare_subsets(exp[i]), 0.0)

        tree1 = TreeNode.read(['(((a,b),(c,d)),((e,f,g),h));'])
        tree2 = TreeNode.read(['(a,((b,x),(d,y,(f,g,h))));'])
        obs = intersect_trees(tree1, tree2)
        tree1_lap = TreeNode.read(['(((a,b),d),((f,g),h));'])
        tree2_lap = TreeNode.read(['(a,(b,(d,(f,g,h))));'])
        exp = (tree1_lap, tree2_lap)
        for i in range(2):
            self.assertEqual(obs[i].compare_subsets(exp[i]), 0.0)

        # test trees with completely different taxa
        tree1 = TreeNode.read(['((a,b),(c,d));'])
        tree2 = TreeNode.read(['((e,f),(g,h));'])
        msg = 'Trees have no overlapping taxa.'
        with self.assertRaisesRegex(ValueError, msg):
            intersect_trees(tree1, tree2)

        # test trees with duplicated taxa
        tree1 = TreeNode.read(['((a,b),(c,d));'])
        tree2 = TreeNode.read(['((a,a),(b,c));'])
        msg = 'Either tree has duplicated taxa.'
        with self.assertRaisesRegex(ValueError, msg):
            intersect_trees(tree1, tree2)

    def test_unpack_by_func(self):
        """Test unpacking nodes by function."""
        # unpack internal nodes with branch length <= 1.0
        def func(x):
            return x.length <= 1.0

        # will unpack node 'a', but not tip 'e'
        # will add the branch length of 'a' to its child nodes 'c' and 'd'
        tree = TreeNode.read(['((c:2,d:3)a:1,(e:1,f:2)b:2);'])
        obs = str(unpack_by_func(tree, func)).rstrip()
        exp = '((e:1.0,f:2.0)b:2.0,c:3.0,d:4.0);'
        self.assertEqual(obs, exp)

        # unpack internal nodes with branch length < 2.01
        # will unpack both 'a' and 'b'
        obs = str(unpack_by_func(tree, lambda x: x.length <= 2.0)).rstrip()
        exp = '(c:3.0,d:4.0,e:3.0,f:4.0);'
        self.assertEqual(obs, exp)

        # unpack two nested nodes 'a' and 'c' simultaneously
        tree = TreeNode.read(['(((e:3,f:2)c:1,d:3)a:1,b:4);'])
        obs = str(unpack_by_func(tree, lambda x: x.length <= 2.0)).rstrip()
        exp = '(b:4.0,d:4.0,e:5.0,f:4.0);'
        self.assertEqual(obs, exp)

        # test a complicated scenario (unpacking nodes 'g', 'h' and 'm')
        def func(x):
            return x.length < 2.0
        tree = TreeNode.read(['(((a:1.04,b:2.32,c:1.44)d:3.20,'
                              '(e:3.91,f:2.47)g:1.21)h:1.75,'
                              '(i:4.14,(j:2.06,k:1.58)l:3.32)m:0.77);'])
        obs = str(unpack_by_func(tree, func)).rstrip()
        exp = ('((a:1.04,b:2.32,c:1.44)d:4.95,e:6.87,f:5.43,i:4.91,'
               '(j:2.06,k:1.58)l:4.09);')
        self.assertEqual(obs, exp)

        # unpack nodes with support < 75
        def func(x):
            return support(x) < 75
        tree = TreeNode.read(['(((a,b)85,(c,d)78)75,(e,(f,g)64)80);'])
        obs = str(unpack_by_func(tree, func)).rstrip()
        exp = '(((a,b)85,(c,d)78)75,(e,f,g)80);'
        self.assertEqual(obs, exp)

        # unpack nodes with support < 85
        obs = str(unpack_by_func(tree, lambda x: support(x) < 85)).rstrip()
        exp = '((a,b)85,c,d,e,f,g);'
        self.assertEqual(obs, exp)

        # unpack nodes with support < 0.95
        tree = TreeNode.read(['(((a,b)0.97,(c,d)0.98)1.0,(e,(f,g)0.88)0.96);'])
        obs = str(unpack_by_func(tree, lambda x: support(x) < 0.95)).rstrip()
        exp = '(((a,b)0.97,(c,d)0.98)1.0,(e,f,g)0.96);'
        self.assertEqual(obs, exp)

        # test a case where there are branch lengths, none support values and
        # node labels
        def func(x):
            sup = support(x)
            return sup is not None and sup < 75
        tree = TreeNode.read(['(((a:1.02,b:0.33)85:0.12,(c:0.86,d:2.23)'
                              '70:3.02)75:0.95,(e:1.43,(f:1.69,g:1.92)64:0.20)'
                              'node:0.35)root;'])
        obs = str(unpack_by_func(tree, func)).rstrip()
        exp = ('(((a:1.02,b:0.33)85:0.12,c:3.88,d:5.25)75:0.95,'
               '(e:1.43,f:1.89,g:2.12)node:0.35)root;')
        self.assertEqual(obs, exp)

    def test_read_taxdump(self):
        """Test reading NCBI taxdump."""
        obs = read_taxdump(self.nodes_fp)
        exp = {
            '1': {'parent': '1', 'rank': 'order',
                  'children': set(['2', '3'])},
            '2': {'parent': '1', 'rank': 'family',
                  'children': set(['4', '5'])},
            '3': {'parent': '1', 'rank': 'family',
                  'children': set(['6', '7', '8'])},
            '4': {'parent': '2', 'rank': 'genus',
                  'children': set(['9', '10'])},
            '5': {'parent': '2', 'rank': 'genus',
                  'children': set(['11', '12', '13'])},
            '6': {'parent': '3', 'rank': 'genus',
                  'children': set(['14'])},
            '7': {'parent': '3', 'rank': 'genus',
                  'children': set(['15', '16', '17', '18'])},
            '8': {'parent': '3', 'rank': 'genus',
                  'children': set(['19', '20'])},
            '9': {'parent': '4', 'rank': 'species', 'children': set()},
            '10': {'parent': '4', 'rank': 'species', 'children': set()},
            '11': {'parent': '5', 'rank': 'species', 'children': set()},
            '12': {'parent': '5', 'rank': 'species', 'children': set()},
            '13': {'parent': '5', 'rank': 'species', 'children': set()},
            '14': {'parent': '6', 'rank': 'species', 'children': set()},
            '15': {'parent': '7', 'rank': 'species', 'children': set()},
            '16': {'parent': '7', 'rank': 'species', 'children': set()},
            '17': {'parent': '7', 'rank': 'species', 'children': set()},
            '18': {'parent': '7', 'rank': 'species', 'children': set()},
            '19': {'parent': '8', 'rank': 'species', 'children': set()},
            '20': {'parent': '8', 'rank': 'species', 'children': set()}
        }
        for tid in exp:
            exp[tid]['name'] = ''
        self.assertDictEqual(obs, exp)

        obs = read_taxdump(self.nodes_fp, self.names_fp)
        name_dict = {
            '1': 'root', '2': 'Eukaryota', '3': 'Bacteria', '4': 'Plantae',
            '5': 'Animalia', '6': 'Bacteroidetes', '7': 'Proteobacteria',
            '8': 'Firmicutes', '9': 'Gymnosperms', '10': 'Angiosperms',
            '11': 'Chordata', '12': 'Arthropoda', '13': 'Mollusca',
            '14': 'Prevotella', '15': 'Escherichia', '16': 'Vibrio',
            '17': 'Rhizobium', '18': 'Helicobacter', '19': 'Bacillus',
            '20': 'Clostridia'
        }
        for tid in name_dict:
            exp[tid]['name'] = name_dict[tid]
        self.assertDictEqual(obs, exp)

    def test_build_taxdump_tree(self):
        """Test building NCBI taxdump tree."""
        taxdump = read_taxdump(self.nodes_fp)
        obs = build_taxdump_tree(taxdump)
        exp = TreeNode.read(['(((9,10)4,(11,12,13)5)2,((14)6,(15,16,17,18)7,'
                             '(19,20)8)3)1;'])
        self.assertTrue(compare_topology(obs, exp))

    def test_order_nodes(self):
        """Test order nodes"""
        tree1 = TreeNode.read(['(((a,b),(c,d,i)j),((e,g),h));'])
        # test increase ordering
        tree1_increase = order_nodes(tree1, True)
        self.assertTrue(is_ordered(tree1_increase))

        # test decrease ordering
        tree1_decrease = order_nodes(tree1, False)
        self.assertTrue(is_ordered(tree1_decrease, False))

    def test_is_ordered(self):
        """Test if a tree is ordered"""
        # test tree in increasing order
        tree1 = TreeNode.read(['((i,j)a,b)c;'])
        self.assertTrue(is_ordered(tree1))
        self.assertTrue(is_ordered(tree1, True))
        self.assertFalse(is_ordered(tree1, False))

        # test tree in both increasing and decreasing order
        tree2 = TreeNode.read(['(a, b);'])
        self.assertTrue(is_ordered(tree2))
        self.assertTrue(is_ordered(tree2, False))

        # test an unordered tree
        tree3 = TreeNode.read(['(((a,b),(c,d,x,y,z)),((e,g),h));'])
        self.assertFalse(is_ordered(tree3, True))
        self.assertFalse(is_ordered(tree3, False))

        # test tree in decreasing order
        tree5 = TreeNode.read(['((h,(e,g)),((a,b),(c,d,i)j));'])
        self.assertTrue(is_ordered(tree5, False))

    def test_cladistic(self):
        tree1 = TreeNode.read(['((i,j)a,b)c;'])
        self.assertEqual('uni', cladistic(tree1, ['i']))
        self.assertEqual('mono', cladistic(tree1, ['i', 'j']))
        self.assertEqual('poly', cladistic(tree1, ['i', 'b']))
        msg = 'Taxa not found in the tree.'
        with self.assertRaisesRegex(ValueError, msg):
            cladistic(tree1, ['x', 'b'])

        tree2 = TreeNode.read(['(((a,b),(c,d,x)),((e,g),h));'])
        self.assertEqual('uni', cladistic(tree2, ['a']))
        self.assertEqual('mono', cladistic(tree2, ['a', 'b', 'c', 'd', 'x']))
        self.assertEqual('poly', cladistic(tree2, ['g', 'h']))
        with self.assertRaisesRegex(ValueError, msg):
            cladistic(tree2, ['y', 'b'])

    def test_compare_length(self):
        tree = TreeNode.read(['((a:1.000000001,(b:1.000000002,c:1):1):3,f)g;'])
        self.assertTrue(_compare_length(tree.find('f'), tree.find('g')))
        self.assertTrue(_compare_length(tree.find('a'), tree.find('b')))
        self.assertTrue(_compare_length(tree.find('c'), tree.find('c').parent))
        self.assertFalse(_compare_length(tree.find('c'),
                         tree.find('a').parent))
        self.assertFalse(_compare_length(tree.find('a').parent,
                         tree.find('f')))
        self.assertFalse(_compare_length(tree.find('f'),
                         tree.find('a').parent))

    def test_compare_branch_lengths(self):
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree1, tree1))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree2 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree1, tree2))

        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree3 = TreeNode.read(['(f:1,((b:1,c:1)d:1,a:1)e:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree1, tree3))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree3 = TreeNode.read(['(f:1,((b:1,c:1)d:1,a:1)e:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree3, tree1))

        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree4 = TreeNode.read(['((a:2,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree1, tree4))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree4 = TreeNode.read(['((a:2,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree4, tree1))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree5 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree1, tree5))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree5 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree5, tree1))

        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree7 = TreeNode.read(['((a:1,(b:1,c:1):1)e:1,f:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree1, tree7))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree7 = TreeNode.read(['((a:1,(b:1,c:1):1)e:1,f:1)g:1;'])
        self.assertTrue(compare_branch_lengths(tree7, tree1))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree8 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1):1;'])
        self.assertTrue(compare_branch_lengths(tree1, tree8))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree8 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1):1;'])
        self.assertTrue(compare_branch_lengths(tree8, tree1))

        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree6 = TreeNode.read(['(f:1, ((a:1, b:1)c:1 ,d:1)e:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree1, tree6))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree6 = TreeNode.read(['(f:1, ((a:1, b:1)c:1 ,d:1)e:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree6, tree1))

        tree9 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)f:1)g:1,h:1)i:1;'])
        tree10 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)g:1)f:1,h:1)i:1;'])
        self.assertTrue(compare_branch_lengths(tree9, tree10))
        tree9 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)f:1)g:1,h:1)i:1;'])
        tree10 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)g:1)f:1,h:1)i:1;'])
        self.assertTrue(compare_branch_lengths(tree10, tree9))

        tree9 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)f:1)g:1,h:1)i:1;'])
        tree12 = TreeNode.read(['(((a:1,b:1):1,(h:1,e:1):1):1,d:1):1;'])
        self.assertFalse(compare_branch_lengths(tree9, tree12))
        tree9 = TreeNode.read(['(((a:1,b:1)c:1,(d:1,e:1)f:1)g:1,h:1)i:1;'])
        tree12 = TreeNode.read(['(((a:1,b:1):1,(h:1,e:1):1):1,d:1):1;'])
        self.assertFalse(compare_branch_lengths(tree12, tree9))

        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree11 = TreeNode.read(['((a:1,(x:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree1, tree11))
        tree1 = TreeNode.read(['((a:1,(b:1,c:1)d:1)e:1,f:1)g:1;'])
        tree11 = TreeNode.read(['((a:1,(x:1,c:1)d:1)e:1,f:1)g:1;'])
        self.assertFalse(compare_branch_lengths(tree11, tree1))

    def test_walk_copy(self):
        tree1 = TreeNode.read(['(((a:1.0,b:0.8)c:2.4,(d:0.8,e:0.6)f:1.2)g:0.4,'
                               '(h:0.5,i:0.7)j:1.8)k;'])
        assign_supports(tree1)

        # test pos = root
        msg = 'Cannot walk from root of a rooted tree.'
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('k'), tree1.find('j'))
        msg = 'Source and node are not neighbors.'

        # test pos = derived
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('a'), tree1.find('b'))
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('c'), tree1.find('f'))
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('f'), tree1.find('j'))
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('f'), tree1.find('k'))

        # test pos = basal
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('g'), tree1.find('a'))
        with self.assertRaisesRegex(ValueError, msg):
            walk_copy(tree1.find('g'), tree1.find('k'))

        # pos = derived, move = up
        exp = TreeNode.read(['(b:0.8,((d:0.8,e:0.6)f:1.2,(h:0.5,i:0.7)j:2.2)'
                             'g:2.4)c:1.0;'])
        obs = walk_copy(tree1.find('c'), tree1.find('a'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

        # pos = derived, move = down
        exp = TreeNode.read(['(d:0.8,e:0.6)f:1.2;'])
        obs = walk_copy(tree1.find('f'), tree1.find('g'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

        # pos = basal, move = top
        exp = TreeNode.read(['((d:0.8,e:0.6)f:1.2,(h:0.5,i:0.7)j:2.2)g:2.4;'])
        obs = walk_copy(tree1.find('g'), tree1.find('c'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

        # pos = basal, move = bottom
        exp = TreeNode.read(['(h:0.5,i:0.7)j:2.2;'])
        obs = walk_copy(tree1.find('j'), tree1.find('g'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

        tree2 = TreeNode.read(['(((a:1.0,b:0.8)c:2.4,d:0.8)e:0.6,f:1.2,'
                               'g:0.4)h:0.5;'])
        assign_supports(tree2)

        # pos = basal, move = down
        exp = TreeNode.read(['((a:1.0,b:0.8)c:2.4,d:0.8)e:0.6;'])
        obs = walk_copy(tree2.find('e'), tree2.find('h'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

        # pos = basal, move = up
        exp = TreeNode.read(['(d:0.8,(f:1.2,g:0.4)h:0.6)e:2.4;'])
        obs = walk_copy(tree2.find('e'), tree2.find('c'))
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, obs))

    def test_root_above(self):
        tree1 = TreeNode.read(['(((a:1.0,b:0.8)c:2.4,(d:0.8,e:0.6)f:1.2)g:0.4,'
                               '(h:0.5,i:0.7)j:1.8)k;'])
        assign_supports(tree1)

        tree1_cg = root_above(tree1.find('c'))
        exp = TreeNode.read(['((a:1.0,b:0.8)c:1.2,((d:0.8,e:0.6)f:1.2,(h:0.5,'
                             'i:0.7)j:2.2)g:1.2);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree1_cg))

        tree1_ij = root_above(tree1.find('i'))
        exp = TreeNode.read(['(i:0.35,(h:0.5,((a:1.0,b:0.8)c:2.4,(d:0.8,'
                            'e:0.6)f:1.2)g:2.2)j:0.35);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree1_ij))

        # test unrooted tree
        tree2 = TreeNode.read(['(((a:0.6,b:0.5)g:0.3,c:0.8)h:0.4,(d:0.4,'
                               'e:0.5)i:0.5,f:0.9)j;'])
        assign_supports(tree2)

        tree2_ag = root_above(tree2.find('a'))
        exp = TreeNode.read(['(a:0.3,(b:0.5,(c:0.8,((d:0.4,e:0.5)i:0.5,'
                             'f:0.9)j:0.4)h:0.3)g:0.3);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree2_ag))

        tree2_gh = root_above(tree2.find('g'))
        exp = TreeNode.read(['((a:0.6,b:0.5)g:0.15,(c:0.8,((d:0.4,e:0.5)i:0.5,'
                             'f:0.9)j:0.4)h:0.15);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree2_gh))

        # test unrooted tree with 1 basal node
        tree3 = TreeNode.read(['(((a:0.4,b:0.3)e:0.1,(c:0.4,'
                               'd:0.1)f:0.2)g:0.6)h:0.2;'])
        assign_supports(tree3)

        tree3_ae = root_above(tree3.find('a'))
        exp = TreeNode.read(['(a:0.2,(b:0.3,((c:0.4,d:0.1)f:0.2,'
                             'h:0.6)g:0.1)e:0.2);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree3_ae))

        # test support after reroot
        tree4 = TreeNode.read(['(((a:1.0,b:0.8)95:2.4,(d:0.8,e:0.6)100:1.2)'
                               '75:0.4,(h:0.5,i:0.7)98:1.8)75;'])
        assign_supports(tree4)
        exp = TreeNode.read(['((d:0.8,e:0.6)100:0.6,((a:1.0,b:0.8)95:2.4,'
                             '(h:0.5,i:0.7)98:2.2)100:0.6);'])
        assign_supports(exp)
        tree4_d = root_above(tree4.find('d').parent)
        self.assertTrue(_exact_compare(exp, tree4_d))

        tree4_a = root_above(tree4.find('a').parent)
        exp = TreeNode.read(['((a:1.0,b:0.8)95:1.2,((d:0.8,e:0.6)100:1.2,'
                             '(h:0.5,i:0.7)98:2.2)95:1.2);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree4_a))

    def test_exact_compare(self):
        # test name
        tree0 = TreeNode.read(['((e,d)f,(c,(a,b)));'])
        tree1 = TreeNode.read(['(((a,b),c),(d,e)f);'])
        self.assertTrue(_exact_compare(tree1, tree1))
        self.assertFalse(_exact_compare(tree0, tree1))

        # test length
        tree2 = TreeNode.read(['(((a:1,b):2,c:1),(d:1,e:2)f:1);'])
        self.assertTrue(_exact_compare(tree2, tree2))
        self.assertFalse(_exact_compare(tree1, tree2))
        tree3 = TreeNode.read(['(((a:1,b:0.0):2,c:1):0.0,(d:1,e:2)f:1);'])
        self.assertTrue(_exact_compare(tree3, tree3))
        self.assertFalse(_exact_compare(tree2, tree3))

        # test support
        tree4 = TreeNode.read(['(((a:1,b:1)95:2,c:1)98:3,(d:1,e:2)0.0:1);'])
        tree5 = TreeNode.read(['(((a:1,b:1)95:2,c:1)98:3,(d:1,e:2):1);'])
        assign_supports(tree4)
        self.assertTrue(_exact_compare(tree4, tree4))
        self.assertFalse(_exact_compare(tree4, tree5))
        assign_supports(tree5)
        self.assertFalse(_exact_compare(tree4, tree5))

    def test_root_by_outgroup(self):
        tree1 = TreeNode.read(['(((a:1.0,b:0.8)c:2.4,(d:0.8,e:0.6)f:1.2)g:0.4,'
                               '(h:0.5,i:0.7)j:1.8)k;'])
        msg = 'Outgroup is not a subset of tree tips.'
        with self.assertRaisesRegex(ValueError, msg):
            root_by_outgroup(tree1, ['a', 'b', 'c', 'd', 'e', 'h', 'i'])

        assign_supports(tree1)

        tree2 = root_by_outgroup(tree1, ['a', 'b'])
        exp = TreeNode.read(['((a:1.0,b:0.8)c:1.2,((d:0.8,e:0.6)f:1.2,(h:0.5,'
                             'i:0.7)j:2.2)g:1.2);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree2))

        tree3 = root_by_outgroup(tree1, ['a', 'b', 'h'])
        exp = TreeNode.read(['(((a:1.0,b:0.8)c:2.4,(h:0.5,i:0.7)j:2.2)g:0.6,'
                             '(e:0.6,d:0.8)f:0.6);'])
        assign_supports(exp)
        self.assertTrue(_exact_compare(exp, tree3))


if __name__ == '__main__':
    main()
