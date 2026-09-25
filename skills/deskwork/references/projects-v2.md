# Projects v2

Projects v2 is GraphQL only - there is no REST equivalent. All interactions flow through four entry points: `board.fields()`, `board.items()`, `board.add_item()` and `board.set_field()`. Each wraps a GraphQL call and translates authentication errors into `MissingScope`.

## Identifiers

One GitHub issue carries several identifiers and none of them is interchangeable:

| Identifier | Looks like | Used by |
|---|---|---|
| Issue number | `144` | humans, URLs, `gh issue` commands |
| Database id | `3527190001` | the REST dependencies API, which deskwork does not use |
| GraphQL node id | `"I_kwDOAbc123"` | every Projects v2 mutation |

Dependency edges go through `gh issue edit --add-blocked-by` and `--remove-blocked-by`, which take the issue number and resolve it inside gh. The REST dependencies API takes a database id, links a different issue when handed a number, and still returns 201, so deskwork never calls it. Projects v2 mutations take the node id, which deskwork reads from `gh issue view --json id` and checks against the number it asked for.

## Projects must be addressed by node id

A project is always addressed by node id, never by title. Titles are not unique - a project need not even be linked to the repository. If you address a project by title, `--add-project` silently adds to one of two same-named boards. The project's own node id - returned by `projects list` or a Projects v2 query - is the only unambiguous address.

## Authentication: the project scope

Projects v2 mutations require the `project` scope. This is separate from the `repo` scope and must be granted explicitly:

```bash
gh auth refresh -s project
```

Check the current token's scopes with `gh auth status`.

If a mutation fails because the scope is missing, `board` raises `MissingScope` with the command to fix it. The error message names the fix (`gh auth refresh -s project`) rather than leaking the GraphQL error.

## Mutations

### add_item

Add an issue to a project:

```python
import ids
import board

ref = ids.Ref("owner", "repo", ids.IssueNumber(144))
node = ids.node_id(ref)
item_id = board.add_item("PVT_kwDOABCD1234", node)
```

The issue must be passed as a GraphQL node id. The project must be passed as a GraphQL node id. Returns the item id.

### set_field

Set a single-select field on a project item:

```python
board.set_field("PVT_kwDOABCD1234", item_id, field_id, option_id)
```

Takes four node/field ids returned by `fields()` and `items()`. Returns nothing.

## Queries

### fields

List the fields (columns) in a project:

```python
field_dict = board.fields("PVT_kwDOABCD1234")
```

Returns a dict keyed by field name, with each entry holding the field's id, name, and options (for single-select fields). The key is the field's display name; the id is a GraphQL node id for use in `set_field()`.

### items

List the issues in a project:

```python
item_list = board.items("PVT_kwDOABCD1234")
```

Returns a list of items, each holding the item's id, the issue's number/repository/state, and the field values on that item. Filtered to exclude draft items (which have no `content`).
