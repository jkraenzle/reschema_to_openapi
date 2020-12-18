import os
import re
import sys
from typing import Any, IO
import yaml

# ---- YAML helper functions -----
# Define YAML Loader, as default Loader is not safe
class YAMLLoader(yaml.SafeLoader):
	"""YAML Loader with `!include` constructor."""

	def __init__(self, stream: IO) -> None:
		"""Initialise Loader."""

		try:
			self._root = os.path.split(stream.name)[0]
		except AttributeError:
			self._root = os.path.curdir

		super().__init__(stream)


def construct_include(loader: YAMLLoader, node: yaml.Node) -> Any:
	"""Include file referenced at node."""

	filename = os.path.abspath(os.path.join(loader._root, loader.construct_scalar(node)))
	extension = os.path.splitext(filename)[1].lstrip('.')

	with open(filename, 'r') as f:
		if extension in ('yaml', 'yml'):
			return yaml.load(f, YAMLLoader)


yaml.add_constructor('!include', construct_include, YAMLLoader)

def yamlread (fn):
	try:
		if fn != None:
			with open(fn) as fh:
				yamlresult = yaml.load (fh, YAMLLoader)
		else:
			yamlresult = None
	except FileNotFoundError as err:
		yamlresult = None

	return yamlresult

def yamlwrite (data, fn):
	try:
		if fn != None:
			with open(fn, 'w') as fh:
				fileresult = yaml.dump (data, fh)
		else:
			fileresult = None
	except IOError as err:
		fileresult = None

	return fileresult

# -----

def openapi_refreplace (ref):

	if ref.find ('#/types', 0) != -1:
		newref = ref.replace ('#/types', '#/components/schemas')
	elif ref.find ('#/resources', 0) != -1:
		newref = ref.replace ('#/resources', '#/components/schemas')
	else:
		newref = ref

	return newref

def openapischema_refreplace (property):
	propertyref = property.pop ('$ref', None)
	if propertyref != None:
		openapi_propertyref = openapi_refreplace (propertyref)
		property['$ref'] = openapi_propertyref

	return property	

def openapischema_propertyupdate (properties):
	for property_key in properties:
		property = properties[property_key]
	
		# Remove 'cpptype' and other 'C-level' flags
		tags = property.pop ('tags', None)
		# Remove 'relations' for now
		relations = property.pop ('relations', None)

		# Remove required if there are no entries
		if 'required' in property:
			if len(property['required']) == 0:
				required = property.pop ('required', None)

		# Iterate and update references in properties, subproperties, and array objects
		if 'type' in property:
			type = property['type']
			if type == 'array':
				property = property['items']

				if 'properties' in property:
					subproperties = property['properties'].copy ()
					property['properties'] = openapischema_propertyupdate (subproperties)

				# Remove 'cpptype' and other 'C-level' flags
				tags = property.pop ('tags', None)
				relations = property.pop ('relations', None)

				if '$ref' in property:
					property = openapischema_refreplace (property)

			elif type == 'object':
				if 'properties' in property:
					subproperties = property['properties'].copy () 
					property['properties'] = openapischema_propertyupdate (subproperties)
				property = openapischema_refreplace (property)
			elif type == 'timestamp':
				property['type'] = 'number'
			elif type == 'null':
				property['type'] = 'string'

		# Handle case where reference is directly made without property type
		else:
			if '$ref' in property:
				property = openapischema_refreplace (property)
		
		# Handle 'oneOf' or 'anyOf'		
		if 'oneOf' in property or 'anyOf' in property:
			if 'oneOf' in property:
				ofkey = 'oneOf'
			elif 'anyOf' in property:
				ofkey = 'anyOf'
			
			options = property[ofkey]
			for option in options:
				tags = option.pop ('tags', None)
				if 'type' in option and option['type'] == 'null':
					option['type'] = 'string'

		# Handle $merge values
		property_definition = property.pop ('$merge', None)
		if property_definition != None:
			allof_property = []
			
			if 'source' in property_definition and '$ref' in property_definition['source']:
				propertyone = {}
				propertyone['$ref'] = property_definition['source']['$ref']
				propertyone = openapischema_refreplace (propertyone)
				allof_property.append (propertyone)

			if 'description' in property_definition:
				propertytwo = {}
				propertytwo['description'] = property_definition['with']['description']
				allof_property.append (propertytwo)
			elif 'relations' in property_definition:
				propertytwo = {}
				propertytwo['description'] = property_definition['relations']['full']['description']
				allof_property.append (propertytwo)

			properties[property_key] = {'allOf': allof_property}

	return properties

def openapischema_update (openapi_schema):
	if 'type' in openapi_schema:
		type = openapi_schema['type']
		if type == 'object' or type == 'string' or type == 'integer':
			if 'tags' in openapi_schema:
				tags = openapi_schema.pop ('tags', None)
			 # Remove required if there are no entries
			if 'required' in openapi_schema:
				if len(openapi_schema['required']) == 0:
					required = openapi_schema.pop ('required', None)

			if 'properties' in openapi_schema:
				properties = openapi_schema['properties'].copy ()
				openapi_schema['properties'] = openapischema_propertyupdate (properties)
			if 'oneOf' in openapi_schema or 'anyOf' in openapi_schema:
				if 'oneOf' in openapi_schema:
					ofkey = 'oneOf'
				elif 'anyOf' in openapi_schema:
					ofkey = 'anyOf'

				if 'properties' in openapi_schema[ofkey]:
					properties = openapi_schema[ofkey]['properties'].copy ()
					openapi_schema[ofkey]['properties'] = openapischema_propertyupdate (properties)
				options = openapi_schema[ofkey]
				for option in options:
					tags = option.pop ('tags', None)
					if 'type' in option and option['type'] == 'null':
						option['type'] = 'string'
						
		elif type == 'array':
			schema = openapi_schema.copy ()

			while type == 'array':
				save_schema = None
				if 'items' in schema:
					save_schema = schema
					schema = schema ['items']
				if 'type' in schema:
					type = schema['type']
					if type == 'object':
						if 'properties' in schema:
							properties = schema['properties']
							schema['properties'] = openapischema_propertyupdate (properties)
				else:
					# Handle the case with no 'type' object but just '$ref'
					if '$ref' in schema:
						schema = openapischema_refreplace (schema)
						type = 'none'

				# For now, remove relations and tags
				if 'relations' in schema:
					relations = schema.pop ('relations', None)
				if 'tags' in schema:
					tags = schema.pop ('tags', None)

				if save_schema != None:
					save_schema ['items'] = schema

			if save_schema != None:			
				openapi_schema = save_schema
			else:
				openapi_schema = schema

	return openapi_schema

def path_parse (path):
	parameters = []
	queryparameters = []

	groups = re.findall (r'{(.*?)}', path)
	if len (groups) == 0:
		return None, None

	for group in groups:
		if group[0] == '?':
			terms = group.split (',')
			for term in terms:
				queryparameter = term.strip ('? ')
				queryparameters.append (queryparameter)	
		else:
			parameters.append (group)

	return parameters, queryparameters

def openapi_from_reschema (reschema_files):

	openapi_files = []

	for reschema_file in reschema_files:
		print (reschema_file)
		reschema_dict = yamlread (reschema_file)
		api_path = '/' + reschema_dict['name'] + '/' + reschema_dict['version']

		# Create the template
		openapi_dict = {
			'openapi':'3.0.2',
			'info': {
				'title': reschema_dict ['title'],
				'version': reschema_dict ['version']
			},
			'servers': [
				{
				'url': "https://{URL}:{Port}/api/",
				'variables': {
					'URL': {'default':"abc.example.com"},
					'Port': {'enum': ['443'], 'default': '443'}
				},
				'description': "Example API base path for URL"
				}
			],
			'paths': {},
			'components': {
				'securitySchemes': {
					'oAuth2NoScopes': {
						'description': 'Credential approach to retrieving token',
						'type': 'oauth2',
						'flows': {
							'clientCredentials': {
								'tokenUrl': '/mgmt.aaa/1.0/token',
								'refreshUrl': '/mgmt.aaa/1.0/token',
								'scopes': {}
							}
						}
					},
					'bearerAuth': {
						'description': 'Access token approach to reaching appliance',
						'type': 'http',
						'scheme': 'bearer',
						'bearerFormat': 'JWT'
					}
				}
			},
			'security': [
				{'oAuth2NoScopes': []},
				{'bearerAuth': []}
			]
		}
		
		# Update optional settings that are missing in some files
		if 'description' in reschema_dict:
			openapi_dict['info']['description'] = reschema_dict['description']

		# Resource in OpenAPI is a schema and a path; handle conversion to both
		# Prepare return structures to assign back to template
		openapi_schemas = {}
		openapi_paths = {}
		openapi_path_parameters = None
		openapi_path_queryparameters = None

		# Pull and iterate over the resources from reschema to convert to paths
		resources = reschema_dict ['resources']
		for resource_key in resources:

			# First, convert the resources to components/schema
			# Copy the original resource and remove/replace the relevant data
			openapi_schema = resources[resource_key].copy ()

			# Remove the links for future use as these are paths in the OpenAPI spec
			links = openapi_schema.pop ('links', None)

			# Remove 'C' tags for now
			tags = openapi_schema.pop ('tags', None)
	
			# Remove relations for now, as they are currently applied to schema rather than response as in OpenAPI specification
			relations = openapi_schema.pop ('relations', None)

			# Update any object references
			openapi_schema = openapischema_update (openapi_schema)

			# Add this resource as a schema
			openapi_schemas [resource_key] = openapi_schema

			# Second, handle default path for resources using popped link data
			# Find the root path from the 'self' data
			openapi_path = resource_tag = None

			for link_key in links:
				if link_key == 'self':
					# Find default path for actions
					path = links[link_key]['path']
					if isinstance(path,dict) and 'template' in path:
						path = path['template']
						openapi_path = api_path + path.strip(' $')
					else:
						openapi_path = api_path + path.strip(' $')

					# Parse path to identify if it contains parameters or query parameters
					openapi_path_parameters, openapi_path_queryparameters = path_parse (openapi_path)

					# Find resource tag to use for documentation
					if path.find('$/',0) == 0:
						if path.find('/',2) == -1:
							resource_tag = path[path.find('/',0) + 1:]
						else:
							resource_tag = path[path.find('/',0) + 1:path.find('/',2)]
					break

			# Third, now that we have the path, pull the different actions, methods, parameters, and query parameters
			for link_key in links:
				openapi_subpath_parameters = None
				openapi_subpath_queryparameters = None

				# Already found this so continue; this could be more efficient by building up a data structure while iterating to find the path
				if link_key == 'self':
					continue
				else: # For all other links, use the path provided by 'self' unless 'path' is provided explicitly
					openapi_subpath = None
					if 'path' in links[link_key]:
						subpath = links[link_key]['path']
						# Check if subpath has query string, otherwise handle more quickly
						if isinstance(subpath, dict):
							if 'template' in subpath:
								template = subpath['template'].strip(' $')
								openapi_subpath_parameters, openapi_subpath_queryparameters = path_parse (template)
								openapi_subpath = api_path + template
						else:
							subpath = subpath.strip(' $')
							openapi_subpath_parameters, openapi_subpath_queryparameters = path_parse (subpath)
							openapi_subpath = api_path + subpath

					# Find method, action, and request and response information for path
					method_summary = link_key
					method_action = links[link_key]['method']
					openapi_action = method_action.lower ()
					
					has_request = 'request' in links[link_key]
					if has_request:
						if '$ref' in links[link_key]['request']:
							method_requestref = links[link_key]['request']['$ref']
							openapi_requestref = openapi_refreplace (method_requestref)
							openapi_request = {
								'required': True,
								'content': {
									'application/json': {
										'schema': {
											'type': 'object',
											'properties': {
												'items': {
													'type': 'array',
													'items': {'$ref': openapi_requestref}
												}
											}
										}
									}
								}
							}
						else:
							schema = links[link_key]['request'].copy ()
							openapi_schema = openapischema_update (schema)
							openapi_request = {
								'required': True, 
								'content': {
									'application/json': {
										'schema': openapi_schema
									}
								}
							}

					has_response = 'response' in links[link_key]			
					if has_response:
						if '$ref' in links[link_key]['response']:
							method_responseref = links[link_key]['response']['$ref']
							openapi_responseref = openapi_refreplace(method_responseref)
							openapi_response = {
								'200': {
									'description': '',
									'content': {
										'application/json': {
											'schema': {
												'type': 'array',
												'items': {'$ref': openapi_responseref}
											}
										}
									}
								}
							}
						else:
							openapi_response = {
								'200': {
									'description': '',
									'content': {
										'application/json': {
											'schema': {}
										}
									}
								}
							}
							response_schema = links[link_key]['response'].copy () 						
							openapi_response_schema = openapi_response['200']['content']['application/json']['schema'].copy ()
							for setting in response_schema:
								if setting not in ['description', 'properties', 'items']:
									openapi_response_schema [setting] = response_schema [setting]
								elif setting == 'description':
									openapi_response['200']['description'] = response_schema ['description']
								elif setting == 'properties':
									openapi_response_schema ['properties'] = openapischema_propertyupdate (response_schema ['properties'])
								elif setting == 'items':
									openapi_response_schema ['items'] = response_schema ['items']
									if '$ref' in openapi_response_schema ['items']:
										openapi_response_schema ['items']['$ref'] = openapi_refreplace (openapi_response_schema['items']['$ref'])
								
							openapi_response['200']['content']['application/json']['schema'] = openapi_response_schema
		
					if openapi_subpath != None:
						path_key = openapi_subpath
						parameters = openapi_subpath_parameters
						queryparameters = openapi_subpath_queryparameters
					elif openapi_path != None:
						path_key = openapi_path
						parameters = openapi_path_parameters
						queryparameters = openapi_path_queryparameters

					# Clean path to not include queryparameters
					path_key = path_key.split('?', 1)[0]
					if path_key[-1] == '{':
						path_key = path_key[:-1]

					# Create the path if it does not exist, or re-use it if it does
					path_method_and_tags = {openapi_action: {'summary': method_summary, 'tags': [resource_tag]}} 
					if path_key in openapi_paths:	
						openapi_paths [path_key].update (path_method_and_tags)
					else:
						openapi_paths [path_key] = path_method_and_tags
					if has_response:
						openapi_paths [path_key][openapi_action]['responses'] = openapi_response
					else:
						openapi_paths [path_key][openapi_action]['responses'] = {'200':{'description':'On success, the server does not provide any body in the response.'}}
					if has_request:
						openapi_paths [path_key][openapi_action]['requestBody'] = openapi_request
					if parameters != None and len(parameters) > 0:
						openapi_paths [path_key][openapi_action]['parameters'] = []
						for parameter in parameters:
							if parameter in resources[resource_key]['properties'] and \
								'description' in resources[resource_key]['properties'][parameter]:
								description = resources[resource_key]['properties'][parameter]['description']
							else:
								description = ''
							openapi_paths [path_key][openapi_action]['parameters'].append (
								{'in':'path', 'name':parameter, 'schema':{'type':'string'}, 'required':True, 'description':description}
							)
					if queryparameters != None and len(queryparameters) > 0:
						if 'parameters' not in openapi_paths[path_key][openapi_action]:
							openapi_paths[path_key][openapi_action]['parameters'] = []
						for queryparameter in queryparameters:
							if queryparameter in links[link_key]['path']['vars']:
								if 'description' in links[link_key]['path']['vars'][queryparameter]:
									description = links[link_key]['path']['vars'][queryparameter]['description']
								else:
									description = ''
								if 'type' in links[link_key]['path']['vars'][queryparameter]:
									type = links[link_key]['path']['vars'][queryparameter]['type']
								else:
									type='string'
							openapi_paths[path_key][openapi_action]['parameters'].append (
								{'in':'query', 'name':queryparameter, 'schema':{'type':type}, 'required':False, 'description':description}
							)

		openapi_dict['components']['schemas'] = openapi_schemas
		openapi_dict['paths'] = openapi_paths

		# Pull the types from reschema to convert to schemas
		if 'types' in reschema_dict:
			types = reschema_dict ['types']
			openapi_schemas = {}
			for type_key in types:
				# Copy exact format and make changes, rather than re-create
				openapi_schema = types[type_key].copy () # Index rather than iterate as value to be clear what its copying

				# Replace any object references
				openapi_schema = openapischema_update (openapi_schema)

				openapi_schemas[type_key] = openapi_schema
						
			openapi_dict['components']['schemas'].update(openapi_schemas)

		# Write output file
		openapi_filename = os.path.join("openapi", "openapi-" + os.path.basename (reschema_file))
		print (openapi_filename)
		openapi_file = yamlwrite (openapi_dict, openapi_filename)
		if openapi_file != None:
			openapi_files.append (openapi_filename)

	return openapi_files


def main ():

	subdirectory_files = os.listdir ("public")
	input_files = []
	for file in subdirectory_files:
		input_file = os.path.join ("public", file)
		input_files.append (input_file)
	openapi_files = openapi_from_reschema (input_files)

if __name__ == "__main__":
	main ()
