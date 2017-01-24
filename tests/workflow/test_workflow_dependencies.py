# -*- coding: utf-8 -*-

import pytest
import networkx as nx
import json
import matplotlib.pyplot as plt

from juicer.workflow.workflow import Workflow

def debug_instance(instance_wf):
    print
    print '*' * 20
    print instance_wf.workflow_graph.nodes()
    print '*' * 21
    print instance_wf.workflow_graph.edges()
    print '*' * 22
    print instance_wf.workflow_graph.is_multigraph()
    print '*' * 23
    print instance_wf.workflow_graph.number_of_edges()
    print '*' * 24
    print instance_wf.sorted_tasks
    print '*' * 25
    test = instance_wf.get_reversed_graph()
    print test.edges()
    print '*' * 26
    print instance_wf.workflow_graph.in_degree()
    print instance_wf.check_in_degree_edges()
    print '*' * 27
    print instance_wf.workflow_graph.out_degree()
    print instance_wf.check_out_degree_edges()
    print '*' * 28

    # Show image
    # pos = nx.spring_layout(instance_wf.workflow_graph)
    # pos = nx.fruchterman_reingold_layout(instance_wf.workflow_graph)
    # nx.draw(instance_wf.workflow_graph, pos, node_color='#004a7b', node_size=2000,
    #         edge_color='#555555', width=1.5, edge_cmap=None,
    #         with_labels=True, style='dashed',
    #         label_pos=50.3, alpha=1, arrows=True, node_shape='s',
    #         font_size=8,
    #         font_color='#FFFFFF')
    # plt.show()
    # plt.savefig(filename, dpi=300, orientation='landscape', format=None,
                 # bbox_inches=None, pad_inches=0.1)


def test_workflow_sequence_missing_outdegree_edge_failure():
    workflow_test = json.load(
        open("./tests/workflow/workflow_missing_out_degree_edge.txt"),
        encoding='utf-8')

    instance_wf = Workflow(workflow_test)

    with pytest.raises(AttributeError):
        instance_wf.check_out_degree_edges()

def test_workflow_sequence_outdegree_edge_success():
    workflow_test = json.load(
        open("./tests/workflow/workflow_out_degree_edge_success.txt"),
        encoding='utf-8')

    instance_wf = Workflow(workflow_test)

    instance_wf.check_out_degree_edges()

    assert 1 == instance_wf.check_out_degree_edges()



def test_workflow_sequence_missing_indegree_edge_success():
    workflow_test = json.load(
        open("./tests/workflow/workflow_in_degree_edge_success.txt"),
        encoding='utf-8')
    instance_wf = Workflow(workflow_test)

    instance_wf.check_in_degree_edges()
    print debug_instance(instance_wf)
    assert instance_wf, debug_instance(instance_wf)

def test_workflow_sequence_success():

    # workflow_completo
    workflow_test = json.load(open("./tests/workflow/workflow_correct_changedid.txt"),
                              encoding='utf-8')

    # workflow_test = json.dumps(json.load(
        # open("./tests/workflow/workflow_correct_changedid.txt"), encoding='utf-8'))

    instance_wf = Workflow(workflow_test)

    # sorted_tasks_id = nx.topological_sort(instance_wf, reverse=False)
    # print sorted_tasks_id

    print debug_instance(instance_wf)
    assert instance_wf, debug_instance(instance_wf)

def test_workflow_sequence_missing_targetid_value_failure():

    # workflow with missing target_id
    workflow_test = json.load(open("./tests/workflow/workflow_missing_targetid.txt"))
    with pytest.raises(AttributeError):
        Workflow(workflow_test)

def test_workflow_sequence_missing_sourceid_value_failure():

    # workflow with missing target_id
    workflow_test = json.load(open("./tests/workflow/workflow_missing_sourceid.txt"))
    with pytest.raises(AttributeError):
        Workflow(workflow_test)


def test_workflow_check_out_degree_node_success():
    return 0

def test_workflow_sequence_missing_edges_failure():
    return 0

def test_workflow_sequence_multiplicity_many_success():
    return 0

def test_workflow_sequence_multiplicity_one_success():
    return 0