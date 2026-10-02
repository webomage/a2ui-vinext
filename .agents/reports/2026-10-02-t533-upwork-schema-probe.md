# Upwork MCP schema probe (T533 AC1)

Key names and tool metadata only. No value from any response is printed. Read-only: `tools/list` and `action: get`.

## Tools offered (51)

| tool | actions | parameters | summary |
|---|---|---|---|
| `upwork__agency_rooms` | add_member, remove_member, update | action, org_uid, params | Agency-only writes to message room settings and membership. Does not list rooms, read messages, or send chat (get_messages / send_message). Obtain room_id from  |
| `upwork__boost_profile` | create_profile_boost, get_status, manage_profile_boost, toggle_availability_badge | action, org_uid, params | Read and wind down freelancer profile visibility boosters: availability badge (PIB) and profile boost ad. Starting or increasing ad spend is done on upwork.com, |
| `upwork__confirm_attachment_upload` | confirm | action, org_uid, params | Confirm uploaded files so they are retained in Upwork storage. Uses the same attachment backends as start_attachment_upload. Requires the upload context and the |
| `upwork__confirm_draft` | confirm | action, org_uid, params | Deprecated alias of confirm_preview (identical behaviour) — prefer confirm_preview. For job postings specifically: confirming a create_draft preview (type='job_ |
| `upwork__confirm_preview` | confirm | action, org_uid, params | Confirm and execute a previously prepared preview for job postings, proposals, invitation accepts, invitations, milestones, profile updates, and offer decline / |
| `upwork__end_contract` | end | action, org_uid, params | End a contract with a reason code, optionally attaching a freelancer review (six 1–5 scores + a comment). Runs through MCP (draft -> confirm_preview). Use list_ |
| `upwork__find_freelancers` | get_profile, search, smart_search | action, org_uid, params | Freelancers on the marketplace: search them by keywords and filters, get the freelancers recommended for one of your job postings (smart_search), or view one pr |
| `upwork__find_jobs` | get, search, smart_search | action, org_uid, params | Marketplace job postings: search them by keywords and filters, get one by id, or get the jobs recommended for the freelancer's own profile (smart_search). |
| `upwork__find_saved_jobs` | count, list | action, org_uid, params | Browse your saved (favorite) job postings. Each saved job includes a ready-to-use url. Use find_jobs action=get for full job details. Use save_job action=save o |
| `upwork__get_account` | get_company, get_organization, get_user_details, list_members, list_teams | action, org_uid, params | View account info, organization details, teams and the member roster. |
| `upwork__get_agency` | get_profile, list_agencies, list_members, list_projects, list_teams | action, org_uid, params | View your agency: teams, members, portfolio projects, and organization details. To change the portfolio, use update_agency. Use get_messages list_rooms to view  |
| `upwork__get_agency_dashboard` | check | action, org_uid, params | Get a consolidated overview of what's new: invitations, offers, messages, matching jobs, contracts, plus agency teams and members — all in one call. Access is s |
| `upwork__get_client_dashboard` | check | action, org_uid, params | Get a consolidated overview of what's new: proposals received (grouped by job), pending offers, messages, and contract updates — all in one call. |
| `upwork__get_client_financials` | snapshots, summary, timesheets, transactions, work_days, work_diary | action, org_uid, params | View client financial reports: timesheets, work diaries, work-diary snapshots, and transaction history. transactions may require elevated org permissions. |
| `upwork__get_draft` | get | action, org_uid, params | Deprecated alias of get_preview (identical behaviour) — prefer get_preview. |
| `upwork__get_freelancer_dashboard` | check | action, org_uid, params | Get a consolidated overview of what's new: invitations, offers, messages, matching jobs, contract updates, and connects balance — all in one call. |
| `upwork__get_freelancer_financials` | available_balance, connects_balance, summary, timesheets, transactions | action, org_uid, params | View your own financial data as a freelancer or agency: the balance available to withdraw right now, earnings and transaction history, connects balance, and tim |
| `upwork__get_job_posting` | get, list | action, org_uid, params | View the job postings your organization owns. Use action=list to obtain posting IDs for list_client_proposals and list_client_invitations. Prior postings are us |
| `upwork__get_messages` | find_room, get_message, list_messages, list_rooms, search_rooms | action, org_uid, params | List rooms, find rooms by context, and read messages. |
| `upwork__get_preview` | get | action, org_uid, params | Retrieve a pending server-stored preview without consuming it. |
| `upwork__get_profile` | connects_balance, get, list_highlights, transactions | action, org_uid, params | View freelancer profile, transaction history, and connects balance. |
| `upwork__get_rate_insights` | get | action, org_uid, params | Get the going hourly rate range for similar jobs to guide a job's hourly budget — the same From/To range Upwork shows in the Budget step. Read-only. Use it whil |
| `upwork__get_tool_help` | - | tool_name | Get the full reference for a tool: its complete description and input schema, including every action and all required and optional parameters. Call this before  |
| `upwork__get_upload_status` | get | action, org_uid, params | Returns file_uid values for files a user uploaded through the web UI. Action name is get (not get_status). Upload sessions expire 30 minutes after start_attachm |
| `upwork__invite_freelancer` | list_jobs, send | action, org_uid, params | Invite a freelancer to a job posting. Use list_jobs to see your jobs and how many invites remain on each, then send (confirm_preview type='invitation'). |
| `upwork__list_accounts` | - | - | List your available Upwork accounts (Freelancer, Client, Agency). Call this first. |
| `upwork__list_client_invitations` | history, list | action, org_uid, params | List or get client job invitations for one owned job posting. Requires job_reference from get_job_posting action=list (postings[].id). Invitations are per-job o |
| `upwork__list_client_proposals` | get, list, list_all, metadata | action, org_uid, params | View proposals received on your job postings. Use action=list_all to discover proposals across all postings without a job_posting_id. Use action=list when you a |
| `upwork__list_contracts` | end_reasons, get, list, search, timesheets | action, org_uid, params | View and search your contracts and time reports. ID provenance: use action=search to discover rows; for CLIENT search results use node.contract.id (not node.id) |
| `upwork__list_freelancer_proposals` | get, get_room, invitations, list | action, org_uid, params | View your freelancer proposals and received invitations. Prior proposals are useful examples when drafting new proposals. Note: the status 'Accepted' means the  |
| `upwork__list_milestones` | list | action, org_uid, params | View milestone state for a fixed-price contract. Returns each milestone's state (NotFunded, Active, Submitted, Paid, …), deposit/funded/paid amounts (both rawVa |
| `upwork__list_offers` | get, get_attachments, list, list_mine | action, org_uid, params | View and list offers. Use list_mine to see all offers for your org. Use get to fetch full details of a specific offer. The 'id' from these results is the offer_ |
| `upwork__manage_client_proposals` | decline, decline_reasons, shortlist | action, org_uid, params | Manage proposals on your job postings while reviewing applicants: shortlist/un-shortlist and decline. To HIRE an applicant, use manage_offers create_draft inste |
| `upwork__manage_meetings` | cancel, free_slots, list, request, reschedule, schedule | action, org_uid, params | Schedule video meetings with the other party in a message room. One side requests a meeting of a set length and the other picks a time from the requester's book |
| `upwork__manage_milestones` | activate, approve, create, delete, edit, reject | action, org_uid, params | WRITE milestone management. create, edit, delete, and reject run through MCP (draft -> confirm_preview). fund (activate) and approve move money — funding escrow |
| `upwork__manage_offers` | acknowledge_policy, create_draft, get, list, withdraw | action, org_uid, params | Create draft offers and manage offers to freelancers. |
| `upwork__manage_proposals` | accept_invitation, acknowledge_policy, create, decline_invitation, edit_terms, send_proposal, withdraw | action, org_uid, params | Submit, edit, or withdraw freelancer proposals. Submitting can include a Connects boost bid for a top slot on the client's list. Also accept or decline client j |
| `upwork__manage_talent_lists` | create_list, delete_list, list_lists, list_talents, lists_for_talent, save, unsave | action, org_uid, params | Save freelancers to your talent lists ("Your Lists"), create lists, and browse the freelancers in a list. Get freelancer_id (personId) from find_freelancers. |
| `upwork__post_job` | close, close_reasons, create_draft, renew, update | action, org_uid, params | Create or update a job posting. create_draft returns a preview for review; confirm_preview on it only saves a real DRAFT and never publishes. To publish, call u |
| `upwork__respond_to_offer` | accept, decline, request_changes | action, org_uid, params | Accept, decline, or request changes to a client offer. Use this tool for all offer responses. 'decline' and 'request_changes' run through MCP (draft -> confirm_ |
| `upwork__save_job` | hide, hide_status, save, unhide, unsave | action, org_uid, params | Manage your own marketplace job lists: save (favorite) a job to come back to it, or hide a job to keep it out of your search results. Both lists are private — t |
| `upwork__send_message` | create_room, edit, message_proposal, send, send_to_user | action, org_uid, params | Create rooms and send messages. message is max 10240 characters — if the user's text is longer, ask them to shorten it rather than sending it truncated. Each fi |
| `upwork__set_tool_mode` | get, set | action, org_uid, params | View or change how MCP tools are presented. full_list shows all tools directly; search_execute uses search_tools/execute_tool indirection. |
| `upwork__set_tool_permission` | get, set | action, org_uid, params | View or change per-tool write confirmation settings. Write tools default to 'always_ask'. Set 'always_allow' to let an agent run a specific tool without asking  |
| `upwork__start_attachment_upload` | upload | action, org_uid, params | Requests a secure file upload from the user. Creates a short-lived upload session and returns task_id plus fallback_url. In MCP App-capable hosts, an inline upl |
| `upwork__store_uploaded_files` | - | files, org_uid, task_id | App-only tool that persists files uploaded through the inline MCP App UI. The model does not call this tool. |
| `upwork__submit_milestones` | submit | action, org_uid, params | Submit milestones for client review. Use this to request approval on completed milestone work. |
| `upwork__update_account` | create_team, invite_member, rename_team, update_company_details, update_company_location, update_company_profile | action, org_uid, params | CLIENT account only: change the company name, description, tagline, website, business location, industry, size, profile visibility and occupations freelancers s |
| `upwork__update_agency` | create_project, delete_project, reorder_projects, update_project | action, org_uid, params | Change your agency: portfolio projects (add, edit, reorder, remove). Read the current state with get_agency. |
| `upwork__update_contract` | pause, restart, update_hourly_limit | action, org_uid, params | Update contract conditions. pause and restart run through MCP (draft -> confirm_preview). Changing the weekly hours limit is completed by you on Upwork and retu |
| `upwork__update_profile` | add_education, add_employment, add_language, add_other_experience, remove_education, remove_employment, remove_language, remove_other_experience, set_skills, set_video, update_availability, update_education, update_employment, update_language, update_other_experience, update_overview, update_title | action, org_uid, params | Manage freelancer profile: title, overview, video introduction, availability, employment, skills, languages, education, and other experience. |

## Which tool covers which topic

| topic | tools |
|---|---|
| proposal | `upwork__confirm_preview`, `upwork__get_client_dashboard`, `upwork__get_job_posting`, `upwork__list_client_proposals`, `upwork__list_freelancer_proposals`, `upwork__manage_client_proposals`, `upwork__manage_proposals` |
| offer | `upwork__confirm_preview`, `upwork__get_agency_dashboard`, `upwork__get_client_dashboard`, `upwork__get_freelancer_dashboard`, `upwork__list_offers`, `upwork__manage_client_proposals`, `upwork__manage_offers`, `upwork__respond_to_offer` |
| contract | `upwork__end_contract`, `upwork__get_agency_dashboard`, `upwork__get_client_dashboard`, `upwork__get_freelancer_dashboard`, `upwork__list_contracts`, `upwork__list_milestones`, `upwork__update_contract` |
| room | `upwork__agency_rooms`, `upwork__get_agency`, `upwork__get_agency_dashboard`, `upwork__get_client_dashboard`, `upwork__get_client_financials`, `upwork__get_freelancer_dashboard`, `upwork__get_freelancer_financials`, `upwork__get_messages`, `upwork__get_profile`, `upwork__manage_meetings`, `upwork__send_message` |
| job | `upwork__confirm_draft`, `upwork__confirm_preview`, `upwork__find_freelancers`, `upwork__find_jobs`, `upwork__find_saved_jobs`, `upwork__get_agency_dashboard`, `upwork__get_client_dashboard`, `upwork__get_freelancer_dashboard`, `upwork__get_job_posting`, `upwork__get_rate_insights`, `upwork__invite_freelancer`, `upwork__list_client_invitations`, `upwork__list_client_proposals`, `upwork__manage_client_proposals`, `upwork__post_job`, `upwork__save_job` |
| client | `upwork__get_account`, `upwork__get_agency`, `upwork__get_client_dashboard`, `upwork__get_client_financials`, `upwork__get_job_posting`, `upwork__list_accounts`, `upwork__list_client_invitations`, `upwork__list_client_proposals`, `upwork__list_contracts`, `upwork__manage_client_proposals`, `upwork__manage_proposals`, `upwork__respond_to_offer`, `upwork__submit_milestones`, `upwork__update_account` |

## Proposal fields (5 of 5 fetched)

### Returned by the source and NOT stored in our database

- `annotations`
- `auditDetails`
- `auditDetails.createdDateTime`
- `auditDetails.createdDateTime.displayValue`
- `auditDetails.createdDateTime.rawValue`
- `auditDetails.modifiedDateTime`
- `auditDetails.modifiedDateTime.displayValue`
- `auditDetails.modifiedDateTime.rawValue`
- `boosted`
- `marketplaceJobPosting`
- `marketplaceJobPosting.content`
- `marketplaceJobPosting.content.title`
- `marketplaceJobPosting.id`
- `marketplaceJobPosting.url`
- `questionsAnswers`
- `questionsAnswers[].answer`
- `questionsAnswers[].question`
- `status.reason`
- `status.reason.id`
- `status.reason.reason`
- `status.status`
- `status.status_label`
- `terms`
- `terms.chargeRate`
- `terms.chargeRate.currency`
- `terms.chargeRate.displayValue`
- `terms.chargeRate.rawValue`
- `terms.connectsBid`

### Stored in our database but not returned by the source in this sample

- `client_country`
- `context`
- `createdDateTime`
- `exported_at`
- `jobId`
- `jobPosting`
- `jobPosting.id`
- `jobPosting.title`
- `modifiedDateTime`
- `proposalId`
- `roomId`
- `tags`
- `title`
- `type`

### Every key path returned

- `annotations`
- `auditDetails`
- `auditDetails.createdDateTime`
- `auditDetails.createdDateTime.displayValue`
- `auditDetails.createdDateTime.rawValue`
- `auditDetails.modifiedDateTime`
- `auditDetails.modifiedDateTime.displayValue`
- `auditDetails.modifiedDateTime.rawValue`
- `boosted`
- `id`
- `marketplaceJobPosting`
- `marketplaceJobPosting.content`
- `marketplaceJobPosting.content.title`
- `marketplaceJobPosting.id`
- `marketplaceJobPosting.url`
- `proposalCoverLetter`
- `questionsAnswers`
- `questionsAnswers[].answer`
- `questionsAnswers[].question`
- `status`
- `status.reason`
- `status.reason.id`
- `status.reason.reason`
- `status.status`
- `status.status_label`
- `terms`
- `terms.chargeRate`
- `terms.chargeRate.currency`
- `terms.chargeRate.displayValue`
- `terms.chargeRate.rawValue`
- `terms.connectsBid`

## Does the MCP token work on the GraphQL API?

**inconclusive**: HTTP 403 with a body that is not GraphQL JSON, which looks like a firewall page rather than the API's own answer.

HTTP status: 403. GraphQL errors: no. No token and no id is printed or stored.
