# Project Rules and Guidelines

## Ecosystem Context

The `wom7api` project is a backend capability layer within a larger monorepo structure. Before modifying inter-service API patterns or architectural integrations, you MUST consult the core ecosystem maps located in the sibling repository:
- `../wom7web/docs/ECOSYSTEM.md`

## Local Development

- **Dev Server**: Always run `just redev` before performing local checks or manual testing. This ensures the environment is clean and running on the assigned port.
- **Local URL**: All local testing must be conducted on **http://localhost:4321**. Avoiding other ports or `127.0.0.1` unless specifically required.
- **Authentication**: Be aware that Google OAuth may redirect to the live domain during local testing due to Supabase callback restrictions.

## Deployment

- **Pre-deployment Checks**: Always run `just check-auth` before triggering a deployment to ensure the current environment is authorized for the target Supabase project.
- **Verification**: Run `just verify` after significant changes to ensure codebase integrity.

## Testing & Manual Verification

- **Start Dev Server First**: You MUST start `just redev` before running any manual tests or visual debug verifications to ensure the dev server is fully available and clean.
- **Admin Credentials**: Always use the `ADMIN_EMAIL` and `ADMIN_PASSWORD` credentials found in `wom7web/.env` for logging into the Control Panel during testing. Forget about any legacy `testadmin` accounts.
- **Environment Variables**: Always use `ADMIN_*` environment variables for test setups to ensure they are distinct from production credentials.
