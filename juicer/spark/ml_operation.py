# coding=utf-8
import json
import logging
from itertools import izip_longest
from textwrap import dedent

from juicer.operation import Operation, ReportOperation

log = logging.getLogger()
log.setLevel(logging.DEBUG)


class FeatureIndexerOperation(Operation):
    """
    A label indexer that maps a string attribute of labels to an ML attribute of
    label indices (attribute type = STRING) or a feature transformer that merges
    multiple attributes into a vector attribute (attribute type = VECTOR). All
    other attribute types are first converted to STRING and them indexed.
    """
    ATTRIBUTES_PARAM = 'attributes'
    TYPE_PARAM = 'indexer_type'
    ALIAS_PARAM = 'alias'
    MAX_CATEGORIES_PARAM = 'max_categories'

    TYPE_STRING = 'string'
    TYPE_VECTOR = 'vector'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)
        '''
        del parameters['workflow_json']
        print '-' * 30
        print parameters.keys()
        print '-' * 30
        '''
        if self.ATTRIBUTES_PARAM in parameters:
            self.attributes = parameters.get(self.ATTRIBUTES_PARAM)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.ATTRIBUTES_PARAM, self.__class__))
        self.type = self.parameters.get(self.TYPE_PARAM, self.TYPE_STRING)
        self.alias = [alias.strip() for alias in
                      parameters.get(self.ALIAS_PARAM, '').split(',')]

        if self.MAX_CATEGORIES_PARAM in parameters:
            self.max_categories = int(parameters.get(self.MAX_CATEGORIES_PARAM))
            if not (self.max_categories >= 0):
                msg = "Parameter '{}' must be in " \
                      "range [x>=0] for task {}" \
                    .format(self.MAX_CATEGORIES_PARAM, __name__)
                raise ValueError(msg)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.MAX_CATEGORIES_PARAM, self.__class__))

        # Adjust alias in order to have the same number of aliases as attributes
        # by filling missing alias with the attribute name sufixed by _indexed.
        self.alias = [x[1] or '{}_indexed'.format(x[0]) for x in
                      izip_longest(self.attributes,
                                   self.alias[:len(self.attributes)])]

    def generate_code(self):
        input_data = self.named_inputs['input data']
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))

        if self.type == self.TYPE_STRING:
            models = self.named_outputs.get('indexer models',
                                            'models_task_{}'.format(self.order))
            code = """
                col_alias = dict({alias})
                indexers = [feature.StringIndexer(inputCol=col, outputCol=alias,
                                handleInvalid='skip')
                                    for col, alias in col_alias.items()]

                # Use Pipeline to process all attributes once
                pipeline = Pipeline(stages=indexers)
                {models} = dict([(c, indexers[i].fit({input})) for i, c in
                                enumerate(col_alias)])

                # Spark ML 2.0.1 do not deal with null in indexer.
                # See SPARK-11569
                {input}_without_null = {input}.na.fill(
                    'NA', subset=col_alias.keys())

                {out} = pipeline.fit({input}_without_null)\
                    .transform({input}_without_null)
            """.format(input=input_data, out=output, models=models,
                       alias=json.dumps(zip(self.attributes, self.alias),
                                        indent=None))
        elif self.type == self.TYPE_VECTOR:
            code = """
                col_alias = dict({3})
                indexers = [feature.VectorIndexer(maxCategories={4},
                                inputCol=col, outputCol=alias)
                                    for col, alias in col_alias.items()]

                # Use Pipeline to process all attributes once
                pipeline = Pipeline(stages=indexers)
                models = dict([(col, indexers[i].fit({1})) for i, col in
                                enumerate(col_alias)])
                labels = None

                # Spark ML 2.0.1 do not deal with null in indexer.
                # See SPARK-11569
                {1}_without_null = {1}.na.fill('NA', subset=col_alias.keys())

                {2} = pipeline.fit({1}_without_null).transform({1}_without_null)
            """.format(self.attributes, input_data, output,
                       json.dumps(zip(self.attributes, self.alias)),
                       self.max_categories)
        else:
            # Only if the field be open to type
            raise ValueError(
                "Parameter type has an invalid value {}".format(self.type))

        return dedent(code)

    def get_output_names(self, sep=','):
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))
        models = self.named_outputs.get('indexer models',
                                        'models_task_{}'.format(self.order))
        return sep.join([output, models])

    def get_data_out_names(self, sep=','):
        return self.named_outputs.get('output data',
                                      'out_task_{}'.format(self.order))


class IndexToStringOperation(Operation):
    ATTRIBUTES_PARAM = 'attributes'
    ALIAS_PARAM = 'alias'
    ORIGINAL_NAMES_PARAM = 'original_names'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)

        if self.ATTRIBUTES_PARAM in parameters:
            self.attributes = parameters.get(self.ATTRIBUTES_PARAM)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.ATTRIBUTES_PARAM, self.__class__))

        if self.ORIGINAL_NAMES_PARAM in parameters:
            self.original_names = parameters.get(self.ORIGINAL_NAMES_PARAM)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.ORIGINAL_NAMES_PARAM, self.__class__))
        self.alias = [alias.strip() for alias in
                      parameters.get(self.ALIAS_PARAM, '').split(',')]

        # Adjust alias in order to have the same number of aliases as attributes
        # by filling missing alias with the attribute name sufixed by _indexed.
        self.alias = [x[1] or '{}_str'.format(x[0]) for x in
                      izip_longest(self.attributes,
                                   self.alias[:len(self.attributes)])]
        self.has_code = 'input data' in self.named_inputs

    def generate_code(self):
        input_data = self.named_inputs['input data']
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))
        models = self.named_inputs.get('indexer models')
        if models is not None:
            labels = '{models}[original_names[i]].labels'.format(models=models)
        else:
            labels = '[]'

        code = """
            original_names = {original_names}
            col_alias = dict({alias})
            converter = [feature.IndexToString(inputCol=col,
                                               outputCol=alias,
                                               labels={labels})
                        for i, (col, alias) in enumerate(col_alias.items())]

            # Use Pipeline to process all attributes once
            pipeline = Pipeline(stages=converter)
            {out} = pipeline.fit({input}).transform({input})
        """.format(input=input_data, out=output, labels=labels,
                   original_names=json.dumps(
                       [n.strip() for n in self.original_names]),
                   alias=json.dumps(zip(self.attributes, self.alias),
                                    indent=None))
        return dedent(code)


class OneHotEncoderOperation(Operation):
    """
    One hot encoding transforms categorical features to a format that works
    better with classification and regression algorithms.
    """
    ATTRIBUTES_PARAM = 'attributes'
    ALIAS_PARAM = 'alias'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)

        if self.ATTRIBUTES_PARAM in parameters:
            self.attributes = parameters.get(self.ATTRIBUTES_PARAM)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.ATTRIBUTES_PARAM, self.__class__))
        self.alias = [alias.strip() for alias in
                      parameters.get(self.ALIAS_PARAM, '').split(',')]

        # Adjust alias in order to have the same number of aliases as attributes
        # by filling missing alias with the attribute name sufixed by _indexed.
        self.alias = [x[1] or '{}_indexed'.format(x[0]) for x in
                      izip_longest(self.attributes,
                                   self.alias[:len(self.attributes)])]

    def generate_code(self):
        input_data = self.named_inputs['input data']
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))

        code = """
            col_alias = dict({aliases})
            encoders = [feature.OneHotEncoder(inputCol=col, outputCol=alias,
                            dropLast=True)
                        for col, alias in col_alias.items()]

            # Use Pipeline to process all attributes once
            pipeline = Pipeline(stages=encoders)
            {out} = pipeline.fit({input}).transform({input})
            """.format(input=input_data, out=output,
                       aliases=json.dumps(zip(self.attributes, self.alias),
                                          indent=None))
        return dedent(code)

    def get_output_names(self, sep=','):
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))
        return output

    def get_data_out_names(self, sep=','):
        return self.named_outputs.get('output data',
                                      'out_task_{}'.format(self.order))


class FeatureAssemblerOperation(Operation):
    """
    A feature transformer that merges multiple attributes into a vector
    attribute.
    """
    ATTRIBUTES_PARAM = 'attributes'
    ALIAS_PARAM = 'alias'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        if self.ATTRIBUTES_PARAM in parameters:
            self.attributes = parameters.get(self.ATTRIBUTES_PARAM)
        else:
            raise ValueError(
                "Parameter '{}' must be informed for task {}".format(
                    self.ATTRIBUTES_PARAM, self.__class__))
        self.alias = parameters.get(self.ALIAS_PARAM, 'features')

        self.has_code = len(self.named_inputs) > 0

    def generate_code(self):
        input_data = self.named_inputs['input data']
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))

        code = """
            assembler = feature.VectorAssembler(inputCols={0}, outputCol="{1}")
            {3}_without_null = {3}.na.drop(subset={0})
            {2} = assembler.transform({3}_without_null)
        """.format(json.dumps(self.attributes), self.alias, output,
                   input_data)

        return dedent(code)


class ApplyModelOperation(Operation):
    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.has_code = len(self.named_inputs) == 2

    def generate_code(self):
        input_data1 = self.named_inputs['input data']
        output = self.named_outputs.get('output data',
                                        'out_task_{}'.format(self.order))

        model = self.named_inputs.get(
            'model', 'model_task_{}'.format(self.order))

        code = "{out} = {in2}.transform({in1})".format(
            out=output, in1=input_data1, in2=model)

        return dedent(code)


class EvaluateModelOperation(Operation):
    PREDICTION_ATTRIBUTE_PARAM = 'prediction_attribute'
    LABEL_ATTRIBUTE_PARAM = 'label_attribute'
    METRIC_PARAM = 'metric'

    METRIC_TO_EVALUATOR = {
        'areaUnderROC': (
            'evaluation.BinaryClassificationEvaluator', 'rawPredictionCol'),
        'areaUnderPR': (
            'evaluation.BinaryClassificationEvaluator', 'rawPredictionCol'),
        'f1': ('evaluation.MulticlassClassificationEvaluator', 'predictionCol'),
        'weightedPrecision': (
            'evaluation.MulticlassClassificationEvaluator', 'predictionCol'),
        'weightedRecall': (
            'evaluation.MulticlassClassificationEvaluator', 'predictionCol'),
        'accuracy': (
            'evaluation.MulticlassClassificationEvaluator', 'predictionCol'),
        'rmse': ('evaluation.RegressionEvaluator', 'predictionCol'),
        'mse': ('evaluation.RegressionEvaluator', 'predictionCol'),
        'mae': ('evaluation.RegressionEvaluator', 'predictionCol'),
    }

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        # @FIXME: validate if metric is compatible with Model using workflow

        self.prediction_attribute = (parameters.get(
            self.PREDICTION_ATTRIBUTE_PARAM) or [''])[0]
        self.label_attribute = (parameters.get(
            self.LABEL_ATTRIBUTE_PARAM) or [''])[0]
        self.metric = parameters.get(self.METRIC_PARAM) or ''

        if all([self.prediction_attribute != '', self.label_attribute != '',
                self.metric != '']):
            pass
        else:
            msg = "Parameters '{}', '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.PREDICTION_ATTRIBUTE_PARAM, self.LABEL_ATTRIBUTE_PARAM,
                self.METRIC_PARAM, self.__class__))
        if self.metric in self.METRIC_TO_EVALUATOR:
            self.evaluator = self.METRIC_TO_EVALUATOR[self.metric][0]
            self.param_prediction_arg = self.METRIC_TO_EVALUATOR[self.metric][1]
        else:
            raise ValueError('Invalid metric value {}'.format(self.metric))

        self.has_code = (
            (len(self.named_inputs) > 0 and len(self.named_outputs) > 0) or
            (self.named_outputs.get('evaluator') is not None) or
            (len(self.named_inputs) == 2)
        )
        self.metric_out = self.named_outputs.get(
            'metric', 'metric_task_{}'.format(self.order))

        self.evaluator_out = self.named_outputs.get(
            'evaluator', 'evaluator_task_{}'.format(self.order))

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=", "):
        return sep.join([self.metric_out, self.evaluator_out])

    def generate_code(self):

        if self.has_code:
            limonero_conf = self.config['juicer']['services']['limonero']
            caipirinha_conf = self.config['juicer']['services']['caipirinha']

            code = ''

            comment = self.parameters['task']['forms'].get('comment',
                                                           {'value': ''}).get(
                'value') or ''
            # Not being used with a cross validator
            if len(self.named_inputs) > 0:
                code = """
                # Creates the evaluator according to the model
                # (user should not change it)
                {evaluator_out} = None
                evaluator = {evaluator}(
                    {pred_col}='{pred_attr}',
                    labelCol='{label_attr}',
                    metricName='{metric}')

                {output} = evaluator.evaluate({input})

                # HTML visualization of result
                from juicer.spark.vis_operation import HtmlVisModel
                from juicer.service import caipirinha_service

                vis_model = dedent('''
                    <div>
                        <strong>{comment}</strong>
                        <dl>
                            <dt>{metric}</dl>
                            <dd>{{0}}</dd>
                        </dl>
                    </div>
                ''').format({output})
                visualizations = [
                {{
                    'job_id': '{job_id}',
                    'task_id': '{task_id}',
                    'title': '{title}',
                    'type': {{
                        'id': {operation_id},
                        'name': '{operation_name}'
                    }},
                    'model': HtmlVisModel(vis_model, '{task_id}',
                        {operation_id},'{operation_name}', '{title}',
                        '[]', '', '', '')
                }}]

                # Basic information to connect to other services
                config = {{
                    'juicer': {{
                        'services': {{
                            'limonero': {{
                                'url': '{limonero_url}',
                                'auth_token': '{limonero_token}'
                            }},
                            'caipirinha': {{
                                'url': '{caipirinha_url}',
                                'auth_token': '{caipirinha_token}',
                                'storage_id': {storage_id}
                            }},
                        }}
                    }}
                }}
                caipirinha_service.new_dashboard(config, '{title}', {user},
                    {workflow_id}, '{workflow_name}',
                    {job_id}, '{task_id}', visualizations, emit_event)

                """.format(output=self.metric_out,
                           comment=comment,
                           input=self.named_inputs['input data'],
                           pred_attr=self.prediction_attribute,
                           label_attr=self.label_attribute,
                           metric=self.metric,
                           evaluator=self.evaluator,
                           evaluator_out=self.evaluator_out,
                           pred_col=self.param_prediction_arg,
                           workflow_id=self.parameters['workflow_id'],
                           workflow_name=self.parameters['workflow_name'],
                           job_id=self.parameters['job_id'],
                           task_id=self.parameters['task_id'],
                           operation_id=self.parameters['operation_id'],
                           operation_name=self.__class__.__name__,
                           user=self.parameters['user'],
                           title='Evaluation result',
                           limonero_url=limonero_conf['url'],
                           limonero_token=limonero_conf['auth_token'],
                           caipirinha_url=caipirinha_conf['url'],
                           caipirinha_token=caipirinha_conf['auth_token'],
                           storage_id=caipirinha_conf['storage_id'], )
            elif len(self.named_outputs) > 0:  # Used with cross validator
                code = """
                {evaluator_out} = {evaluator}(
                    {prediction_arg}='{prediction_attr}',
                    labelCol='{label_attr}',
                    metricName='{metric}')
               {metric_out} = None

                """.format(evaluator=self.evaluator,
                           evaluator_out=self.evaluator_out,
                           prediction_arg=self.param_prediction_arg,
                           prediction_attr=self.prediction_attribute,
                           label_attr=self.label_attribute,
                           metric=self.metric, metric_out=self.metric_out)

            return dedent(code)


class CrossValidationOperation(Operation):
    """
    Cross validation operation used to evaluate classifier results using as many
    as folds provided in input.
    """
    NUM_FOLDS_PARAM = 'folds'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)

        self.has_code = len(self.named_inputs) == 3
        self.num_folds = parameters.get(self.NUM_FOLDS_PARAM, 3)

        self.output = self.named_outputs.get(
            'scored data', 'scored_data_task_{}'.format(self.order))
        self.evaluation = self.named_outputs.get(
            'evaluation', 'evaluation_task_{}'.format(self.order))
        self.models = self.named_outputs.get(
            'models', 'models_task_{}'.format(self.order))

    @property
    def get_inputs_names(self):
        return ', '.join([self.named_inputs['algorithm'],
                          self.named_inputs['input data'],
                          self.named_inputs['evaluator']])

    def get_output_names(self, sep=", "):
        return sep.join([self.output, self.evaluation, self.models])

    def get_data_out_names(self, sep=','):
        return sep.join([self.output])

    def generate_code(self):
        code = dedent("""
                grid_builder = tuning.ParamGridBuilder()
                estimator, param_grid = {algorithm}

                for param_name, values in param_grid.items():
                    param = getattr(estimator, param_name)
                    grid_builder.addGrid(param, values)

                evaluator = {evaluator}

                cross_validator = tuning.CrossValidator(
                    estimator=estimator, estimatorParamMaps=grid_builder.build(),
                    evaluator=evaluator, numFolds={folds})
                cv_model = cross_validator.fit({input_data})
                evaluated_data = cv_model.transform({input_data})
                best_model_{output} = cv_model.bestModel
                metric_result = evaluator.evaluate(evaluated_data)
                {evaluation} = metric_result
                {output} = evaluated_data
                {models} = None
                """.format(algorithm=self.named_inputs['algorithm'],
                           input_data=self.named_inputs['input data'],
                           evaluator=self.named_inputs['evaluator'],
                           evaluation=self.evaluation,
                           output=self.output,
                           models=self.models,
                           folds=self.num_folds))

        # If there is an output needing the evaluation result, it must be
        # processed here (summarization of data results)
        needs_evaluation = 'evaluation' in self.named_outputs
        if needs_evaluation:
            eval_code = """
                grouped_result = evaluated_data.select(
                        evaluator.getLabelCol(), evaluator.getPredictionCol())\\
                        .groupBy(evaluator.getLabelCol(),
                                 evaluator.getPredictionCol()).count().collect()
                eval_{output} = {{
                    'metric': {{
                        'name': evaluator.getMetricName(),
                        'value': metric_result
                    }},
                    'estimator': {{
                        'name': estimator.__class__.__name__,
                        'predictionCol': evaluator.getPredictionCol(),
                        'labelCol': evaluator.getLabelCol()
                    }},
                    'confusion_matrix': {{
                        'data': json.dumps(grouped_result)
                    }},
                    'evaluator': evaluator
                }}

                emit_event('task result', status='COMPLETED',
                    identifier='{task_id}', message='Result generated',
                    type='TEXT', title='{title}',
                    task={{'id': '{task_id}' }},
                    operation={{'id': {operation_id} }},
                    operation_id={operation_id},
                    content=json.dumps(eval_{output}))

                """.format(output=self.output,
                           title='Evaluation result',
                           task_id=self.parameters['task_id'],
                           operation_id=self.parameters['operation_id'])
            code = '\n'.join([code, dedent(eval_code)])

        return code


class ClassificationModelOperation(Operation):
    FEATURES_ATTRIBUTE_PARAM = 'features'
    LABEL_ATTRIBUTE_PARAM = 'label'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(named_outputs) > 0 and len(named_inputs) == 2

        if not all([self.FEATURES_ATTRIBUTE_PARAM in parameters,
                    self.LABEL_ATTRIBUTE_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_ATTRIBUTE_PARAM, self.LABEL_ATTRIBUTE_PARAM,
                self.__class__.__name__))

        self.label = parameters.get(self.LABEL_ATTRIBUTE_PARAM)[0]
        self.features = parameters.get(self.FEATURES_ATTRIBUTE_PARAM)[0]

        self.model = named_outputs.get('model',
                                       'model_task_{}'.format(self.order))

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=','):
        return self.model

    def generate_code(self):
        if self.has_code:
            code = """
            algorithm, param_grid = {algo}
            algorithm.setLabelCol('{label}').setFeaturesCol('{feat}')
            {model} = algorithm.fit({train})
            """.format(model=self.model, algo=self.named_inputs['algorithm'],
                       train=self.named_inputs['train input data'],
                       label=self.label, feat=self.features)

            return dedent(code)
        else:
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format('[]inputs',
                                        '[]outputs',
                                        self.__class__))


class ClassifierOperation(Operation):
    """
    Base class for classification algorithms
    """
    GRID_PARAM = 'paramgrid'
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(named_outputs) > 0
        self.name = "BaseClassifier"

        if 'paramgrid' not in parameters:
            raise ValueError(
                'Parameter grid must be informed for classifier {}'.format(
                    self.__class__))

        if not all([self.LABEL_PARAM in parameters['paramgrid'],
                    self.FEATURES_PARAM in parameters['paramgrid']]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters['paramgrid'].get(self.LABEL_PARAM)
        self.attributes = parameters['paramgrid'].get(self.FEATURES_PARAM)

        self.output = self.named_outputs.get('algorithm',
                                             'algo_task_{}'.format(self.order))

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.output

    def generate_code(self):
        if self.has_code:
            param_grid = {
                'featuresCol': self.attributes,
                'labelCol': self.label
            }
            declare = dedent("""
            param_grid = {2}
            # Output result is the classifier and its parameters. Parameters are
            # need in classification model or cross validator.
            {0} = ({1}(), param_grid)
            """).format(self.output, self.name,
                        json.dumps(param_grid, indent=4))

            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class SvmClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.parameters = parameters
        self.has_code = False
        self.name = 'classification.SVM'


class LogisticRegressionClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.parameters = parameters
        self.name = 'classification.LogisticRegression'


class DecisionTreeClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.name = 'classification.DecisionTreeClassifier'


class GBTClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.name = 'classification.GBTClassifier'


class NaiveBayesClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.name = 'classification.NaiveBayes'


class RandomForestClassifierOperation(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.name = 'classification.RandomForestClassifier'


class PerceptronClassifier(ClassifierOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClassifierOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.name = 'classification.MultilayerPerceptronClassificationModel'


class ClassificationReport(ReportOperation):
    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ReportOperation.__init__(self, parameters, named_inputs, named_outputs)
        self.has_code = len(self.named_inputs) > 1
        self.multiple_inputs = True

    def get_data_out_names(self, sep=','):
        return ''

    def generate_code(self):
        code = dedent("{output} = 'ok'".format(output='FIXME'))
        return code


"""
Clustering part
"""


class ClusteringModelOperation(Operation):
    FEATURES_ATTRIBUTE_PARAM = 'features'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(named_outputs) > 0 and len(named_inputs) == 2

        if self.FEATURES_ATTRIBUTE_PARAM not in parameters:
            msg = "Parameter '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_ATTRIBUTE_PARAM, self.__class__))

        self.features = parameters.get(self.FEATURES_ATTRIBUTE_PARAM)[0]

        self.output = self.named_outputs.get('output data',
                                             'out_task_{}'.format(self.order))
        self.model = self.named_outputs.get('model',
                                            'model_task_{}'.format(self.order))

    @property
    def get_inputs_names(self):
        return ', '.join([
            self.named_inputs.get('train input data',
                                  'train_task_{}'.format(self.order)),
            self.named_inputs.get('algorithm',
                                  'algo_task_{}'.format(self.order))])

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return sep.join([self.output, self.model])

    def generate_code(self):

        if self.has_code:
            code = """
            {algorithm}.setFeaturesCol('{features}')
            {model} = {algorithm}.fit({input})
            # There is no way to pass which attribute was used in clustering, so
            # this information will be stored in uid (hack).
            {model}.uid += '|{features}'
            {output} = {model}.transform({input})
            """.format(model=self.model,
                       algorithm=self.named_inputs['algorithm'],
                       input=self.named_inputs['train input data'],
                       output=self.output,
                       features=self.features)

            return dedent(code)


class ClusteringOperation(Operation):
    """
    Base class for clustering algorithms
    """

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)
        self.has_code = len(named_outputs) > 0
        self.name = "BaseClustering"
        self.set_values = []
        self.output = self.named_outputs.get('algorithm',
                                             'algo_task_{}'.format(self.order))

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=','):
        return self.output

    def generate_code(self):
        if self.has_code:
            declare = "{0} = {1}()".format(self.output, self.name)
            code = [declare]
            code.extend(['{0}.set{1}({2})'.format(self.output, name, v)
                         for name, v in self.set_values])
            return "\n".join(code)


class LdaClusteringOperation(ClusteringOperation):
    NUMBER_OF_TOPICS_PARAM = 'number_of_topics'
    OPTIMIZER_PARAM = 'optimizer'
    MAX_ITERATIONS_PARAM = 'max_iterations'
    DOC_CONCENTRATION_PARAM = 'doc_concentration'
    TOPIC_CONCENTRATION_PARAM = 'topic_concentration'

    ONLINE_OPTIMIZER = 'online'
    EM_OPTIMIZER = 'em'

    def __init__(self, parameters, named_inputs, named_outputs):
        ClusteringOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.number_of_clusters = int(parameters.get(
            self.NUMBER_OF_TOPICS_PARAM, 10))
        self.optimizer = parameters.get(self.OPTIMIZER_PARAM,
                                        self.ONLINE_OPTIMIZER)
        if self.optimizer not in [self.ONLINE_OPTIMIZER, self.EM_OPTIMIZER]:
            raise ValueError(
                'Invalid optimizer value {} for class {}'.format(
                    self.optimizer, self.__class__))

        self.max_iterations = parameters.get(self.MAX_ITERATIONS_PARAM, 10)

        self.doc_concentration = self.number_of_clusters * [
            float(parameters.get(self.DOC_CONCENTRATION_PARAM,
                                 self.number_of_clusters)) / 50.0]

        self.topic_concentration = float(
            parameters.get(self.TOPIC_CONCENTRATION_PARAM, 0.1))

        self.set_values = [
            ['DocConcentration', self.doc_concentration],
            ['K', self.number_of_clusters],
            ['MaxIter', self.max_iterations],
            ['Optimizer', "'{}'".format(self.optimizer)],
            ['TopicConcentration', self.topic_concentration],
        ]
        self.has_code = len(named_outputs) > 0
        self.name = "clustering.LDA"


class KMeansClusteringOperation(ClusteringOperation):
    K_PARAM = 'number_of_topics'
    MAX_ITERATIONS_PARAM = 'max_iterations'
    TYPE_PARAMETER = 'type'
    INIT_MODE_PARAMETER = 'init_mode'
    TOLERANCE_PARAMETER = 'tolerance'

    TYPE_TRADITIONAL = 'kmeans'
    TYPE_BISECTING = 'bisecting'

    INIT_MODE_KMEANS_PARALLEL = 'k-means||'
    INIT_MODE_RANDOM = 'random'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClusteringOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.number_of_clusters = parameters.get(self.K_PARAM,
                                                 10)

        self.max_iterations = parameters.get(self.MAX_ITERATIONS_PARAM, 10)
        self.type = parameters.get(self.TYPE_PARAMETER)
        self.tolerance = float(parameters.get(self.TOLERANCE_PARAMETER, 0.001))

        self.set_values = [
            ['MaxIter', self.max_iterations],
            ['K', self.number_of_clusters],
            ['Tol', self.tolerance],
        ]
        if self.type == self.TYPE_BISECTING:
            self.name = "BisectingKMeans"
        elif self.type == self.TYPE_TRADITIONAL:
            if parameters.get(
                    self.INIT_MODE_PARAMETER) == self.INIT_MODE_RANDOM:
                self.init_mode = self.INIT_MODE_RANDOM
            else:
                self.init_mode = self.INIT_MODE_KMEANS_PARALLEL
            self.set_values.append(['InitMode', '"{}"'.format(self.init_mode)])
            self.name = "clustering.KMeans"
        else:
            raise ValueError(
                'Invalid type {} for class {}'.format(
                    self.type, self.__class__))

        self.has_code = len(named_outputs) > 0


class GaussianMixtureClusteringOperation(ClusteringOperation):
    K_PARAM = 'number_of_topics'
    MAX_ITERATIONS_PARAM = 'max_iterations'
    TOLERANCE_PARAMETER = 'tolerance'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ClusteringOperation.__init__(self, parameters, named_inputs,
                                     named_outputs)
        self.number_of_clusters = parameters.get(self.K_PARAM, 10)
        self.max_iterations = parameters.get(self.MAX_ITERATIONS_PARAM, 10)
        self.tolerance = float(parameters.get(self.TOLERANCE_PARAMETER, 0.001))

        self.set_values = [
            ['MaxIter', self.max_iterations],
            ['K', self.number_of_clusters],
            ['Tol', self.tolerance],
        ]
        self.name = "clustering.GaussianMixture"
        self.has_code = len(named_outputs) > 0


class TopicReportOperation(ReportOperation):
    """
    Produces a report for topic identification in text
    """
    TERMS_PER_TOPIC_PARAM = 'terms_per_topic'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        ReportOperation.__init__(self, parameters, named_inputs, named_outputs)
        self.terms_per_topic = parameters.get(self.TERMS_PER_TOPIC_PARAM, 20)

        self.has_code = len(self.named_inputs) == 3

    def generate_code(self):
        code = dedent("""
            topic_df = {model}.describeTopics(maxTermsPerTopic={tpt})
            # See hack in ClusteringModelOperation
            features = {model}.uid.split('|')[1]
            '''
            for row in topic_df.collect():
                topic_number = row[0]
                topic_terms  = row[1]
                print "Topic: ", topic_number
                print '========================='
                print '\\t',
                for inx in topic_terms[:{tpt}]:
                    print {vocabulary}[features][inx],
                print
            '''
            {output} =  {input}
        """.format(model=self.named_inputs['model'],
                   tpt=self.terms_per_topic,
                   vocabulary=self.named_inputs['vocabulary'],
                   output=self.named_outputs.get('output data'),
                   input=self.named_inputs['input data']))
        return code


"""
  Collaborative Filtering part
"""


class RecommendationModel(Operation):
    RANK_PARAM = 'rank'
    MAX_ITER_PARAM = 'max_iter'
    USER_COL_PARAM = 'user_col'
    ITEM_COL_PARAM = 'item_col'
    RATING_COL_PARAM = 'rating_col'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(outputs) > 0 and len(self.inputs) == 2

        if not all([self.RANK_PARAM in parameters['workflow_json'],
                    self.RATING_COL_PARAM in parameters['workflow_json']]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.RANK_PARAM, self.RATING_COL_PARAM,
                self.__class__.__name__))

        self.model = self.named_outputs.get('model')
        output = self.named_outputs.get('output data')
        # self.ratingCol = parameters.get(self.RATING_COL_PARAM)

    @property
    def get_inputs_names(self):
        return ', '.join([self.named_inputs['input data'],
                          self.named_inputs['algorithm']])

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return sep.join([output,
                         self.model])

    def generate_code(self):
        if self.has_code:

            code = """
            # {1}.setRank('{3}').setRatingCol('{4}')
            {0} = {1}.fit({2})

            {output_data} = {0}.transform({2})
            """.format(self.model, self.named_inputs['algorithm'],
                       self.named_inputs['input data'],
                       self.RANK_PARAM, self.RATING_COL_PARAM,
                       output_data=output)

            return dedent(code)
        else:
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format('[]inputs',
                                        '[]outputs',
                                        self.__class__))


class CollaborativeOperation(Operation):
    """
    Base class for Collaborative Filtering algorithm
    """

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(named_outputs) > 0
        self.name = "als"
        self.set_values = []
        # Define outputs and model
        self.output = self.named_outputs.get('output data',
                                             'out_task_{}'.format(self.order))
        self.model = self.named_outputs.get('model', 'model_task_{}'.format(
            self.order))

    @property
    def get_inputs_names(self):
        return ', '.join([self.named_inputs['input data'],
                          self.named_inputs['algorithm']])

    def get_data_out_names(self, sep=','):
        return self.output

    def get_output_names(self, sep=', '):
        return sep.join([self.model])

    def generate_code(self):
        declare = "{0} = {1}()".format(self.output, self.name)
        code = [declare]
        code.extend(['{0}.set{1}({2})'.format(self.output, name, v)
                     for name, v in self.set_values])
        return "\n".join(code)


class AlternatingLeastSquaresOperation(Operation):
    """
        Alternating Least Squares (ALS) matrix factorization.

        The spark algorithm used is based on
        `"Collaborative Filtering for Implicit Feedback Datasets",
        <http://dx.doi.org/10.1109/ICDM.2008.22>`_
    """
    RANK_PARAM = 'rank'
    MAX_ITER_PARAM = 'max_iter'
    USER_COL_PARAM = 'user_col'
    ITEM_COL_PARAM = 'item_col'
    RATING_COL_PARAM = 'rating_col'
    REG_PARAM = 'reg_param'

    IMPLICIT_PREFS_PARAM = 'implicitPrefs'
    ALPHA_PARAM = 'alpha'
    SEED_PARAM = 'seed'
    NUM_USER_BLOCKS_PARAM = 'numUserBlocks'
    NUM_ITEM_BLOCKS_PARAM = 'numItemBlocks'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)

        self.rank = parameters.get(self.RANK_PARAM, 10)
        self.maxIter = parameters.get(self.MAX_ITER_PARAM, 10)
        self.userCol = parameters.get(self.USER_COL_PARAM, 'user_id')[0]
        self.itemCol = parameters.get(self.ITEM_COL_PARAM, 'movie_id')[0]
        self.ratingCol = parameters.get(self.RATING_COL_PARAM, 'rating')[0]

        self.regParam = parameters.get(self.REG_PARAM, 0.1)
        self.implicitPrefs = parameters.get(self.IMPLICIT_PREFS_PARAM, False)

        self.has_code = len(named_outputs) > 0
        self.name = "collaborativefiltering.ALS"


        # Define input and output
        # output = self.named_outputs['output data']
        # self.input = self.named_inputs['train input data']

    def generate_code(self):
        code = dedent("""
                # Build the recommendation model using ALS on the training data
                {algorithm} = ALS(maxIter={maxIter}, regParam={regParam},
                        userCol='{userCol}', itemCol='{itemCol}',
                        ratingCol='{ratingCol}')
                """.format(
            algorithm=self.named_outputs['algorithm'],
            maxIter=self.maxIter,
            regParam=float(self.regParam),
            userCol='{user}'.format(user=self.userCol),
            itemCol='{item}'.format(item=self.itemCol),
            ratingCol='{rating}'.format(rating=self.ratingCol))
        )

        return code


'''
    Logistic Regression Classification
'''


class LogisticRegressionModel(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'
    WEIGHT_COL_PARAM = ''
    MAX_ITER_PARAM = 'max_iter'
    FAMILY_PARAM = 'family'
    PREDICTION_COL_PARAM = 'prediction'

    REG_PARAM = 'reg_param'
    ELASTIC_NET_PARAM = 'elastic_net'

    # Have summaries model with measure results
    TYPE_BINOMIAL = 'binomial'
    # Multinomial family doesn't have summaries model
    TYPE_MULTINOMIAL = 'multinomial'

    TYPE_AUTO = 'auto'

    def __init__(self, parameters, named_inputs,
                 named_outputs):
        Operation.__init__(self, parameters, named_inputs,
                           named_outputs)

        self.has_code = len(outputs) > 0 and len(self.inputs) == 2

        if not all([self.FEATURES_PARAM in parameters['workflow_json'],
                    self.LABEL_PARAM in parameters['workflow_json']]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__.__name__))

        self.model = self.named_outputs.get('model')
        output = self.named_outputs.get('output data')

    @property
    def get_inputs_names(self):
        return ', '.join([self.named_inputs['input data'],
                          self.named_inputs['algorithm']])

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return sep.join([output,
                         self.model])

    def generate_code(self):
        if self.has_code:

            code = """
            {0} = {1}.fit({2})
            {output_data} = {0}.transform({2})
            """.format(self.model, self.named_inputs['algorithm'],
                       self.named_inputs['input data'],
                       output_data=output)

            return dedent(code)
        else:
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format('[]inputs',
                                        '[]outputs',
                                        self.__class__))


# class LogisticRegressionClassifier(Operation):
#     FEATURES_PARAM = 'features'
#     LABEL_PARAM = 'label'
#     WEIGHT_COL_PARAM = 'weight'
#     MAX_ITER_PARAM = 'max_iter'
#     FAMILY_PARAM = 'family'
#     PREDICTION_COL_PARAM = 'prediction'
#
#     REG_PARAM = 'reg_param'
#     ELASTIC_NET_PARAM = 'elastic_net'
#
#     # Have summaries model with measure results
#     TYPE_BINOMIAL = 'binomial'
#     # Multinomial family doesn't have summaries model
#     TYPE_MULTINOMIAL = 'multinomial'
#
#     TYPE_AUTO = 'auto'
#
#     def __init__(self, parameters, named_inputs,
#                  named_outputs):
#         Operation.__init__(self, parameters, inputs, outputs,
#                            named_inputs, named_outputs)
#         self.parameters = parameters
#         self.name = 'classification.LR'
#         self.has_code = len(outputs) > 0
#
#         if not all([self.LABEL_PARAM in parameters,
#                     self.FEATURES_PARAM in parameters]):
#             msg = "Parameters '{}' and '{}' must be informed for task {}"
#             raise ValueError(msg.format(
#                 self.FEATURES_PARAM, self.LABEL_PARAM,
#                 self.__class__))
#
#         self.label = parameters.get(self.LABEL_PARAM)[0]
#         self.attributes = parameters.get(self.FEATURES_PARAM)[0]
#         self.named_outputs.get('output result',
#                                'out_task_{}'.format(self.order))
#         # output = named_outputs['algorithm']
#
#         self.max_iter = parameters.get(self.MAX_ITER_PARAM, 10)
#         self.reg_param = parameters.get(self.REG_PARAM, 0.1)
#         self.weight_col = parameters.get(self.WEIGHT_COL_PARAM, None)
#
#         self.type_family = self.parameters.get(self.FAMILY_PARAM,
#                                                self.TYPE_AUTO)
#
#     def get_data_out_names(self, sep=','):
#         return ''
#
#     def get_output_names(self, sep=', '):
#         return self.named_outputs['output result']
#         # Change it when the named outputs in Tahiti change.
#         # return self.named_outputs['algorithm']
#
#     def generate_code(self):
#         if self.has_code:
#             declare = dedent("""
#             {output} = LogisticRegression(
#                 featuresCol='{features}', labelCol='{label}',
#                 maxIter={max_iter}, regParam={reg_param})
#             """).format(output=output,
#                         features=self.attributes,
#                         label=self.label,
#                         max_iter=self.max_iter,
#                         reg_param=self.reg_param,
#                         weight=self.weight_col)
#
#             # add , weightCol={weight} if exist
#             code = [declare]
#             return "\n".join(code)
#         else:
#             raise ValueError(
#                 'Parameter output must be informed for classifier {}'.format(
#                     self.__class__))


'''
    Regression Algorithms
'''


class RegressionModelOperation(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    MAX_ITER_PARAM = 'max_iter'
    WEIGHT_COL_PARAM = 'weight'
    PREDICTION_COL_PARAM = 'prediction'
    REG_PARAM = 'reg_param'
    ELASTIC_NET_PARAM = 'elastic_net'

    SOLVER_PARAM = 'solver'

    TYPE_SOLVER_AUTO = 'auto'
    TYPE_SOLVER_NORMAL = 'normal'

    # RegType missing -  none (a.k.a. ordinary least squares),    L2 (ridge regression)
    #                    L1 (Lasso) and   L2 + L1 (elastic net)

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)

        self.has_code = len(named_outputs) > 0 and len(named_inputs) == 2

        if not all([self.FEATURES_PARAM in parameters['workflow_json'],
                    self.LABEL_PARAM in parameters['workflow_json']]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__.__name__))

        self.model = self.named_outputs.get('model')
        self.output = self.named_outputs.get('output data',
                                             'out_task_{}'.format(self.order))

    @property
    def get_inputs_names(self):
        return ', '.join([self.named_inputs['train input data'],
                          self.named_inputs['algorithm']])

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return sep.join([self.output,
                         self.model])

    def generate_code(self):
        if self.has_code:

            code = """
            {0} = {1}.fit({2})
            {output_data} = {0}.transform({2})
            """.format(self.model, self.named_inputs['algorithm'],
                       self.named_inputs['train input data'],
                       output_data=self.output)

            return dedent(code)
        else:
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format('[]inputs',
                                        '[]outputs',
                                        self.__class__))


class LinearRegressionOperation(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    MAX_ITER_PARAM = 'max_iter'
    WEIGHT_COL_PARAM = 'weight'
    PREDICTION_COL_PARAM = 'prediction'
    REG_PARAM = 'reg_param'
    ELASTIC_NET_PARAM = 'elastic_net'

    SOLVER_PARAM = 'solver'

    TYPE_SOLVER_AUTO = 'auto'
    TYPE_SOLVER_NORMAL = 'normal'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.LinearRegression'
        self.has_code = len(named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]

        self.max_iter = parameters.get(self.MAX_ITER_PARAM, 10)
        self.reg_param = parameters.get(self.REG_PARAM, 0.1)
        self.weight_col = parameters.get(self.WEIGHT_COL_PARAM, None)

        self.type_solver = self.parameters.get(self.SOLVER_PARAM,
                                               self.TYPE_SOLVER_AUTO)

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.named_outputs['algorithm']

    def generate_code(self):
        if self.has_code:
            declare = dedent("""
            {output} = LinearRegression(
                featuresCol='{features}', labelCol='{label}',
                maxIter={max_iter}, regParam={reg_param})
            """).format(output=self.named_outputs['algorithm'],
                        features=self.attributes,
                        label=self.label,
                        max_iter=self.max_iter,
                        reg_param=self.reg_param)

            # add , weightCol={weight} if exist
            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class GeneralizedLinearRegression(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    PREDICTION_COL_PARAM = 'prediction'
    MAX_ITER_PARAM = 'max_iter'
    WEIGHT_COL_PARAM = 'weight'

    REG_PARAM = 'reg_param'
    LINK_PREDICTION_COL_PARAM = 'link_prediction_col'

    SOLVER_PARAM = 'solver'

    TYPE_SOLVER_IRLS = 'irls'
    TYPE_SOLVER_NORMAL = 'normal'

    FAMILY_PARAM = 'family'

    TYPE_FAMILY_GAUSSIAN = 'gaussian'
    TYPE_FAMILY_BINOMIAL = 'binomial'
    TYPE_FAMILY_POISSON = 'poisson'
    TYPE_FAMILY_GAMMA = 'gamma'

    LINK_PARAM = 'link'

    TYPE_LINK_IDENTITY = 'identity'  # gaussian-poisson-gamma
    TYPE_LINK_LOG = 'log'  # gaussian-poisson-gama
    TYPE_LINK_INVERSE = 'inverse'  # gaussian-gamma
    TYPE_LINK_LOGIT = 'logit'  # binomial-
    TYPE_LINK_PROBIT = 'probit'  # binomial
    TYPE_LINK_CLOGLOG = 'cloglog'  # binomial
    TYPE_LINK_SQRT = 'sqrt'  # poisson

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.GeneralizedLinearRegression'
        self.has_code = len(named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]
        self.named_outputs.get('algorithm', 'algo_task_{}'.format(self.order))

        self.max_iter = parameters.get(self.MAX_ITER_PARAM, 10)
        self.reg_param = parameters.get(self.REG_PARAM, 0.1)
        self.weight_col = parameters.get(self.WEIGHT_COL_PARAM, None)

        self.type_family = self.parameters.get(self.FAMILY_PARAM,
                                               self.TYPE_FAMILY_BINOMIAL)
        self.type_link = self.parameters.get(self.LINK_PARAM)
        self.link_prediction_col = self.parameters.get(
            self.LINK_PREDICTION_COL_PARAM)[0]

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.output

    def generate_code(self):
        if self.has_code:
            declare = dedent("""
            {output} = GeneralizedLinearRegression(featuresCol='{features}',
                                                   labelCol='{label}',
                                                   maxIter={max_iter},
                                                   regParam={reg_param},
                                                   family='{type_family}',
                                                   link='{type_link}',
                                                   linkPredictionCol='{link_col}'
                                                   )
            """).format(output=self.output,
                        features=self.attributes,
                        label=self.label,
                        max_iter=self.max_iter,
                        reg_param=self.reg_param,
                        type_family=self.type_family,
                        type_link=self.type_link,
                        link_col=self.link_prediction_col
                        )
            # add , weightCol={weight} if exist
            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class DecisionTreeRegressionOperation(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    PREDICTION_COL_PARAM = 'prediction'

    MAX_DEPTH_PARAM = 'max_depth'
    MIN_INSTANCE_PER_NODE_PARAM = 'min_instance'
    MIN_INFO_GAIN_PARAM = 'min_info_gain'
    SEED_PARAM = 'seed'

    VARIANCE_COL_PARAM = 'variance_col'
    IMPURITY_PARAM = 'impurity'

    TYPE_IMPURITY_VARIANCE = 'variance'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.DecisionTreeRegressor'
        self.has_code = len(named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]
        self.named_outputs.get('algorithm', 'algo_task_{}'.format(self.order))

        self.max_depth = parameters.get(self.MAX_DEPTH_PARAM, 5)
        self.min_instance = parameters.get(self.MIN_INSTANCE_PER_NODE_PARAM, 1)
        self.min_info_gain = parameters.get(self.MIN_INFO_GAIN_PARAM, 0.0)

        self.prediction_col = self.parameters.get(self.PREDICTION_COL_PARAM)[0]
        self.variance_col = self.parameters.get(self.VARIANCE_COL_PARAM, None)
        self.seed = self.parameters.get(self.SEED_PARAM, None)

        self.impurity = self.parameters.get(self.IMPURITY_PARAM, 'variance')

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.output

    def generate_code(self):
        if self.has_code:
            declare = dedent("""
            {output} = DecisionTreeRegressor(featuresCol='{features}',
                                             labelCol='{label}',
                                             maxDepth={max_iter},
                                             minInstancesPerNode={min_instance},
                                             minInfoGain={min_info},
                                             impurity='{impurity}',
                                             seed={seed},
                                             varianceCol={variance_col}
                                             )
            """).format(output=self.output,
                        features=self.attributes,
                        label=self.label,
                        max_depth=self.max_depth,
                        min_instance=self.min_instance,
                        min_info=self.min_info_gain,
                        impurity=self.impurity,
                        seed=self.seed,
                        variance_col=self.variance_col
                        )
            # add , weightCol={weight} if exist
            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class GradientBoostedTreeRegressionOperation(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    PREDICTION_COL_PARAM = 'prediction'

    MAX_ITER_PARAM = 'max_iter'
    MAX_DEPTH_PARAM = 'max_depth'
    MIN_INSTANCE_PER_NODE_PARAM = 'min_instance'
    MIN_INFO_GAIN_PARAM = 'min_info_gain'
    SEED_PARAM = 'seed'

    VARIANCE_COL_PARAM = 'variance_col'
    IMPURITY_PARAM = 'impurity'

    TYPE_IMPURITY_VARIANCE = 'variance'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.GradientBoostedTreeRegression'
        self.has_code = len(named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]
        self.named_outputs.get('algorithm', 'algo_task_{}'.format(self.order))

        self.max_iter = parameters.get(self.MAX_ITER_PARAM, 10)
        self.max_depth = parameters.get(self.MAX_DEPTH_PARAM, 5)
        self.min_instance = parameters.get(self.MIN_INSTANCE_PER_NODE_PARAM, 1)
        self.min_info_gain = parameters.get(self.MIN_INFO_GAIN_PARAM, 0.0)

        self.prediction_col = self.parameters.get(self.PREDICTION_COL_PARAM)[0]
        self.variance_col = self.parameters.get(
            self.VARIANCE_COL_PARAM, None)[0]
        self.seed = self.parameters.get(self.SEED_PARAM, None)

        self.impurity = self.parameters.get(self.IMPURITY_PARAM, 'variance')

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.output

    def generate_code(self):
        if self.has_code:
            declare = dedent("""
            {output} = GBTRegressor(featuresCol='{features}',
                                             labelCol='{label}',
                                             maxDepth={max_depth},
                                             minInstancesPerNode={min_instance},
                                             minInfoGain={min_info},
                                             impurity={impurity},
                                             seed={seed},
                                             maxIter={max_iter},
                                             varianceCol='{variance_col}'
                                             )
            """).format(output=self.output,
                        features=self.attributes,
                        label=self.label,
                        max_depth=self.max_depth,
                        min_instance=self.min_instance,
                        min_info=self.min_info_gain,
                        impurity=self.impurity,
                        seed=self.seed,
                        max_iter=self.max_iter,
                        variance_col=self.variance_col
                        )
            # add , weightCol={weight} if exist
            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class AFTSurvivalRegressionOperation(Operation):
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    PREDICTION_COL_PARAM = 'prediction'

    MAX_ITER_PARAM = 'max_iter'
    AGR_DETPTH_PARAM = 'aggregation_depth'
    SEED_PARAM = 'seed'
    CENSOR_COL_PARAM = 'censor'
    QUANTILES_PROBABILITIES_PARAM = 'quantile_probabilities'
    QUANTILES_COL_PARAM = 'quantiles_col'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.AFTSurvivalRegression'
        self.has_code = len(named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]
        self.output = named_outputs.get('algorithm',
                                        'algo_task_{}'.format(self.order))

        self.prediction_col = self.parameters.get(self.PREDICTION_COL_PARAM)[0]
        self.max_iter = parameters.get(self.MAX_ITER_PARAM, 10)
        self.agg_depth = parameters.get(self.AGR_DETPTH_PARAM, 1)

        self.censor = self.parameters.get(self.CENSOR_COL_PARAM, 'censor')[0]
        self.quantile_prob = self.parameters.get(
            self.QUANTILES_PROBABILITIES_PARAM, [])
        self.quantile_col = self.parameters.get(self.QUANTILES_COL_PARAM,
                                                'variance')

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        return self.output

    def generate_code(self):
        if self.has_code:
            declare = dedent("""
            {output} = AFTSurvivalRegression(
                featuresCol='{features}',
                 labelCol='{label}',
                 maxIter={max_iter},
                 censorCol='{censor}',
                 quantileProbabilities={quantile_prob},
                 quantilesCol={quantile_col},
                 predictionCol='{prediction_col}',
                 aggregationDepth={agg_depth}
                 )
            """).format(output=self.output,
                        features=self.attributes,
                        label=self.label,
                        max_iter=self.max_iter,
                        censor=self.censor,
                        quantile_prob=self.quantile_prob,
                        quantile_col=self.quantile_col,
                        agg_depth=self.agg_depth,
                        prediction_col=self.prediction_col
                        )
            # add , weightCol={weight} if exist
            code = [declare]
            return "\n".join(code)
        else:
            raise ValueError(
                'Parameter output must be informed for classifier {}'.format(
                    self.__class__))


class IsotonicRegressionOperation(Operation):
    """
        Only univariate (single feature) algorithm supported
    """
    FEATURES_PARAM = 'features'
    LABEL_PARAM = 'label'

    PREDICTION_COL_PARAM = 'prediction'

    WEIGHT_COL_PARAM = 'weight'
    ISOTONIC_PARAM = 'isotonic'

    def __init__(self, parameters, named_inputs, named_outputs):
        Operation.__init__(self, parameters, named_inputs, named_outputs)
        self.parameters = parameters
        self.name = 'regression.IsotonicRegression'
        self.has_code = len(self.named_outputs) > 0

        if not all([self.LABEL_PARAM in parameters,
                    self.FEATURES_PARAM in parameters]):
            msg = "Parameters '{}' and '{}' must be informed for task {}"
            raise ValueError(msg.format(
                self.FEATURES_PARAM, self.LABEL_PARAM,
                self.__class__))

        self.label = parameters.get(self.LABEL_PARAM)[0]
        self.attributes = parameters.get(self.FEATURES_PARAM)[0]
        self.output = named_outputs.get('algorithm')

        self.prediction_col = self.parameters.get(self.PREDICTION_COL_PARAM)[0]
        self.weight_col = parameters.get(self.WEIGHT_COL_PARAM, None)
        self.isotonic = parameters.get(
            self.ISOTONIC_PARAM, True) in (1, '1', 'true', True)

    def get_data_out_names(self, sep=','):
        return ''

    def get_output_names(self, sep=', '):
        # return self.named_outputs['output result']
        # Change it when the named outputs in Tahiti change.
        return self.output

    def generate_code(self):
        declare = dedent("""
        {output} = IsotonicRegression(featuresCol='{features}',
                                      labelCol='{label}',
                                      predictionCol='{prediction_col}',
                                      isotonic={isotonic}
                                      )
        """).format(output=self.output,
                    features=self.attributes,
                    label=self.label,
                    isotonic=self.isotonic,
                    prediction_col=self.prediction_col
                    )
        # add , weightCol={weight} if exist
        code = [declare]
        return "\n".join(code)
