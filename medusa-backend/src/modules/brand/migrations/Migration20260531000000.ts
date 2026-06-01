import { Migration } from "@medusajs/framework/mikro-orm/migrations"

/**
 * Initial Brand-module migration — creates the `brand` table.
 *
 * Hand-written because `npx medusa db:generate brand` needs a live DB to
 * diff against, and local Postgres isn't part of this workflow. Matches
 * the shape Medusa v2 emits for similar tiny modules (e.g. api-key's
 * InitialSetup migration in @medusajs/api-key/dist/migrations/).
 *
 * Columns mirror src/modules/brand/models/brand.ts:
 *   id          text PRIMARY KEY
 *   name        text NOT NULL
 *   handle      text NOT NULL (unique among non-deleted rows)
 *   description text NULL
 *   logo_url    text NULL
 *   created_at, updated_at, deleted_at — soft-delete timestamps
 */
export class Migration20260531000000 extends Migration {
  async up(): Promise<void> {
    this.addSql(
      'create table if not exists "brand" (' +
        '"id" text not null, ' +
        '"name" text not null, ' +
        '"handle" text not null, ' +
        '"description" text null, ' +
        '"logo_url" text null, ' +
        '"created_at" timestamptz not null default now(), ' +
        '"updated_at" timestamptz not null default now(), ' +
        '"deleted_at" timestamptz null, ' +
        'constraint "brand_pkey" primary key ("id")' +
        ');'
    )
    this.addSql(
      'CREATE UNIQUE INDEX IF NOT EXISTS "IDX_brand_handle_unique" ON "brand" (handle) WHERE deleted_at IS NULL;'
    )
  }

  async down(): Promise<void> {
    this.addSql('drop table if exists "brand" cascade;')
  }
}
