"""Projects v2, which is GraphQL only.

The project is always addressed by node id. Titles are not unique, a project
need not be linked to the repository, and --add-project silently adds to one of
two same-named boards.
"""
import gh
import ids


class MissingScope(Exception):
    """The token cannot see Projects. Say so, rather than leaking a GraphQL error."""


def _graphql(query, **variables):
    try:
        return gh.graphql(query, **variables)
    except gh.GhError as error:
        if "read:project" in str(error) or "missing required scopes" in str(error):
            raise MissingScope(
                "Projects v2 needs the project scope, which this token does not "
                "have. Run: gh auth refresh -s project"
            ) from error
        raise


def fields(project_id):
    query = """
    query($project: ID!) {
      node(id: $project) { ... on ProjectV2 {
        fields(first: 50) { nodes {
          ... on ProjectV2SingleSelectField { id name options { id name } }
          ... on ProjectV2Field { id name }
        } }
      } }
    }"""
    data = _graphql(query, project=project_id)
    return {f["name"]: f for f in data["node"]["fields"]["nodes"] if f}


def items(project_id):
    query = """
    query($project: ID!) {
      node(id: $project) { ... on ProjectV2 {
        items(first: 100) { nodes {
          id
          content { ... on Issue { number repository { name owner { login } } state } }
          fieldValues(first: 20) { nodes {
            ... on ProjectV2ItemFieldSingleSelectValue { name field {
              ... on ProjectV2SingleSelectField { name } } }
          } }
        } }
      } }
    }"""
    data = _graphql(query, project=project_id)
    return [node for node in data["node"]["items"]["nodes"] if node.get("content")]


def add_item(project_id, content_id):
    ids.require_node_id(content_id)
    query = """
    mutation($project: ID!, $content: ID!) {
      addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
        item { id }
      }
    }"""
    data = _graphql(query, project=project_id, content=content_id)
    return data["addProjectV2ItemById"]["item"]["id"]


def set_field(project_id, item_id, field_id, option_id):
    query = """
    mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $project, itemId: $item, fieldId: $field,
        value: {singleSelectOptionId: $option}
      }) { projectV2Item { id } }
    }"""
    _graphql(query, project=project_id, item=item_id, field=field_id, option=option_id)


def ensure_field(project_id, name, options):
    """Create a single-select field if it does not exist. Idempotent.

    If the field already exists, it is returned untouched. Returns the field
    dict with id, name, and options.
    """
    # Check if the field already exists
    all_fields = fields(project_id)
    if name in all_fields:
        return all_fields[name]

    # Field does not exist, create it
    query = """
    mutation($project: ID!, $name: String!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
      createProjectV2Field(input: {
        projectId: $project, dataType: SINGLE_SELECT, name: $name,
        singleSelectOptions: $options
      }) { field {
        __typename id name
        ... on ProjectV2SingleSelectField { options { id name } }
      } }
    }"""
    # Convert options list of strings to the mutation format
    option_inputs = [{"name": opt} for opt in options]
    data = _graphql(query, project=project_id, name=name, options=option_inputs)
    field = data["createProjectV2Field"]["field"]
    return {
        "name": field["name"],
        "id": field["id"],
        "options": field.get("options", []),
    }
