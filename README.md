# Vercel Deployments Cleanup (Reusable Action)

This composite GitHub Action cleans up Vercel deployments that are in Building/Queued state by keeping the newest one and deleting the rest.

## Inputs
- vercel_token (required): Vercel CLI token (use GitHub secrets)
- default_projects (optional): comma-separated list of projects to process when `projects` is empty
- projects (optional): comma-separated list to process, overrides `default_projects` when provided
- verbose (optional): `true|false` toggle to print full CLI outputs
- aggressive_cleanup (optional): `true|false` enable last-resort heuristic parsing (use with caution)

## Usage

```yaml
name: Cleanup Vercel Deployments
on:
  push:
    branches: [ main ]
  workflow_dispatch:
    inputs:
      projects:
        description: "Comma-separated Vercel projects"
        required: false
        type: string
      verbose:
        description: "Verbose logs"
        required: false
        type: boolean
        default: false
jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Vercel cleanup
        uses: OWNER/vercel-cleanup-action@v1
        with:
          vercel_token: ${{ secrets.VERCEL_CLI_TOKEN }}
          default_projects: "app-directory"
          projects: ${{ github.event.inputs.projects }}
          verbose: ${{ github.event.inputs.verbose || false }}
```

Note: replace `OWNER/vercel-cleanup-action@v1` with your repository coordinates.

## License
MIT
