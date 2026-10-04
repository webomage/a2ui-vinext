# Upwork messages probe (T539 AC1)

Key names, counts and verdicts only. No id, name, message text or cursor is printed. Read-only: `list_rooms` and `list_messages`.

## Rooms (`list_rooms`)

Items returned for `limit: 2`: 2.

| second page asked by | result |
|---|---|
| `offset` | ignored |
| `cursor` | advances |
| `next_cursor` | ignored |
| `after` | advances |

`advances` = the parameter moves through the list, `ignored` = the server answered with the same first item, `not_offered` = the response carries no cursor, `no_answer` = no items came back.

### Every key path returned

- `data`
- `data.rooms`
- `data.rooms[].awaiting_reply_from`
- `data.rooms[].id`
- `data.rooms[].job`
- `data.rooms[].job.jobId`
- `data.rooms[].job.jobName`
- `data.rooms[].lastActivity`
- `data.rooms[].last_message_from_self`
- `data.rooms[].last_message_side`
- `data.rooms[].latestStory`
- `data.rooms[].latestStory.createdDateTime`
- `data.rooms[].latestStory.id`
- `data.rooms[].latestStory.message`
- `data.rooms[].numUnread`
- `data.rooms[].numUsers`
- `data.rooms[].roomName`
- `data.rooms[].roomType`
- `hasMore`
- `next_cursor`
- `status`
- `trace_id`

## Messages (`list_messages`)

Items returned for `limit: 2`: 2.

| second page asked by | result |
|---|---|
| `offset` | ignored |
| `cursor` | advances |
| `next_cursor` | ignored |
| `after` | advances |

`advances` = the parameter moves through the list, `ignored` = the server answered with the same first item, `not_offered` = the response carries no cursor, `no_answer` = no items came back.

### Every key path returned

- `data`
- `data.roomStories`
- `data.roomStories.edges`
- `data.roomStories.edges[].cursor`
- `data.roomStories.edges[].node`
- `data.roomStories.edges[].node.createdDateTime`
- `data.roomStories.edges[].node.from`
- `data.roomStories.edges[].node.from_my_organization`
- `data.roomStories.edges[].node.from_organization`
- `data.roomStories.edges[].node.from_side`
- `data.roomStories.edges[].node.id`
- `data.roomStories.edges[].node.message`
- `data.roomStories.pageInfo`
- `data.roomStories.pageInfo.endCursor`
- `data.roomStories.pageInfo.hasNextPage`
- `data.roomStories.visibleCount`
- `hasMore`
- `next_cursor`
- `status`
- `trace_id`

## Does reading messages change the room?

Marked read by `list_messages`: no.
