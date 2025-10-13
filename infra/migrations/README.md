# Database Migrations

This directory contains SQL migration scripts for the DispatchAI database schema.

## Migration List

- **001_add_unique_issue_id_constraint.sql** - Adds unique constraint on `enriched_issues.issue_id` to ensure idempotency when resyncing issues

## Applying Migrations

### Development Environment

Run migrations against the local Docker database:

```bash
make migrate
```

Or manually with psql:

```bash
docker exec -i dispatch-ai-postgres-1 psql -U postgres -d dispatchai < infra/migrations/001_add_unique_issue_id_constraint.sql
```

### Production Environment

```bash
psql -h <host> -U <user> -d dispatchai < infra/migrations/001_add_unique_issue_id_constraint.sql
```

## Migration Guidelines

1. **Always test migrations in development first**
2. **Migrations should be idempotent** - safe to run multiple times
3. **Use transactions** - wrap changes in BEGIN/COMMIT
4. **Add verification** - include checks to confirm migration succeeded
5. **Document changes** - include comments explaining purpose and impact
6. **Name consistently** - use format `NNN_descriptive_name.sql`

## Rollback

If a migration needs to be rolled back, create a new migration that reverses the changes. Never modify existing migration files after they've been applied to production.
