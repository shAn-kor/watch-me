"""initial schema

All 13 tables of 02-data-model.md section 2 with every CHECK, partial unique
index and foreign key. Generated with `alembic revision --autogenerate`, then
checked by hand against 02 and by DB-MIG-01 (head == models, same DDL as
`metadata.create_all`).

Revision ID: 0001
Revises:
Create Date: 2026-10-28 15:18:56
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import app.db.types


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('job',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('payload', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=True),
    sa.Column('session_id', sa.String(length=32), nullable=True),
    sa.Column('clip_id', sa.String(length=32), nullable=True),
    sa.Column('dedupe_key', sa.String(length=80), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='queued', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('max_attempts', sa.Integer(), server_default=sa.text('2'), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('run_after', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('locked_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('locked_by', sa.String(length=40), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('updated_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name=op.f('ck_job_status')),
    sa.CheckConstraint("type IN ('transcode', 'transcribe', 'sample', 'draft', 'merge', 'check', 'purge_clip', 'purge_dog', 'retention_sweep')", name=op.f('ck_job_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job')),
    sqlite_autoincrement=True
    )
    op.create_index('ix_job_claim', 'job', ['status', 'run_after'], unique=False)
    op.create_index('ix_job_clip', 'job', ['clip_id'], unique=False)
    op.create_index('ix_job_dog', 'job', ['dog_id'], unique=False)
    op.create_index('uq_job_dedupe', 'job', ['dedupe_key'], unique=True, sqlite_where=sa.text("status IN ('queued', 'running')"))
    op.create_table('org',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('location', sa.String(length=120), nullable=False),
    sa.Column('contact_url', sa.String(length=300), nullable=True),
    sa.Column('contact_email', sa.String(length=254), nullable=True),
    sa.Column('contact_phone', sa.String(length=40), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint('contact_url IS NOT NULL OR contact_email IS NOT NULL OR contact_phone IS NOT NULL', name=op.f('ck_org_has_contact')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_org'))
    )
    op.create_table('member',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.Column('consented_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('consent_version', sa.String(length=20), nullable=True),
    sa.Column('session_epoch', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_login_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("role IN ('staff', 'volunteer')", name=op.f('ck_member_role')),
    sa.CheckConstraint('(consented_at IS NULL) = (consent_version IS NULL)', name=op.f('ck_member_consent_pair')),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_member_email_lower')),
    sa.ForeignKeyConstraint(['org_id'], ['org.id'], name=op.f('fk_member_org_id_org'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_member'))
    )
    op.create_index('ix_member_org', 'member', ['org_id'], unique=False)
    op.create_index('uq_member_email', 'member', ['email'], unique=True)
    op.create_table('dog',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('created_by', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('sex', sa.String(length=8), server_default='unknown', nullable=False),
    sa.Column('age_estimate', sa.String(length=40), nullable=False),
    sa.Column('size', sa.String(length=8), nullable=False),
    sa.Column('photo_path', sa.String(length=300), nullable=True),
    sa.Column('location', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=10), server_default='draft', nullable=False),
    sa.Column('public_slug', sa.String(length=16), nullable=True),
    sa.Column('known_concerns', sa.Text(), nullable=True),
    sa.Column('known_concerns_none', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('people_check_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('people_check_by', sa.String(length=32), nullable=True),
    sa.Column('published_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('adopted_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('deleted_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('updated_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("sex IN ('male', 'female', 'unknown')", name=op.f('ck_dog_sex')),
    sa.CheckConstraint("size IN ('small', 'medium', 'large')", name=op.f('ck_dog_size')),
    sa.CheckConstraint("status <> 'deleted' OR public_slug IS NULL", name=op.f('ck_dog_deleted_no_slug')),
    sa.CheckConstraint("status <> 'published' OR (public_slug IS NOT NULL AND people_check_at IS NOT NULL AND (known_concerns_none = 1 OR length(trim(coalesce(known_concerns, ''))) > 0))", name=op.f('ck_dog_published_checklist')),
    sa.CheckConstraint("status IN ('draft', 'published', 'adopted', 'deleted')", name=op.f('ck_dog_status')),
    sa.CheckConstraint('NOT (known_concerns_none = 1 AND known_concerns IS NOT NULL AND length(trim(known_concerns)) > 0)', name=op.f('ck_dog_concerns_vs_none')),
    sa.CheckConstraint('known_concerns_none IN (0, 1)', name=op.f('ck_dog_known_concerns_none_bool')),
    sa.ForeignKeyConstraint(['created_by'], ['member.id'], name=op.f('fk_dog_created_by_member'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['org_id'], ['org.id'], name=op.f('fk_dog_org_id_org'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['people_check_by'], ['member.id'], name=op.f('fk_dog_people_check_by_member'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dog'))
    )
    op.create_index('ix_dog_org_status', 'dog', ['org_id', 'status'], unique=False)
    op.create_index('uq_dog_slug', 'dog', ['public_slug'], unique=True)
    op.create_table('session',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=False),
    sa.Column('member_id', sa.String(length=32), nullable=False),
    sa.Column('situations', sa.JSON(), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='open', nullable=False),
    sa.Column('fail_code', sa.String(length=20), nullable=True),
    sa.Column('rules_ack_at', app.db.types.UtcDateTime(), nullable=False),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('submitted_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('review_ready_at', app.db.types.UtcDateTime(), nullable=True),
    sa.CheckConstraint("fail_code IS NULL OR fail_code IN ('no_usable_clip', 'merge_failed')", name=op.f('ck_session_fail_code')),
    sa.CheckConstraint("fail_code IS NULL OR status = 'failed'", name=op.f('ck_session_fail_code_only_failed')),
    sa.CheckConstraint("status IN ('open', 'processing', 'review', 'failed')", name=op.f('ck_session_status')),
    sa.CheckConstraint('json_valid(situations) AND json_array_length(situations) BETWEEN 1 AND 8', name=op.f('ck_session_situations_count')),
    sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], name=op.f('fk_session_dog_id_dog'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['member_id'], ['member.id'], name=op.f('fk_session_member_id_member'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_session'))
    )
    op.create_index('ix_session_dog', 'session', ['dog_id'], unique=False)
    op.create_index('ix_session_member', 'session', ['member_id'], unique=False)
    op.create_index('ix_session_status', 'session', ['status'], unique=False)
    op.create_table('clip',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('client_request_id', sa.String(length=40), nullable=True),
    sa.Column('original_filename', sa.String(length=200), nullable=False),
    sa.Column('original_path', sa.String(length=300), nullable=True),
    sa.Column('original_size_bytes', sa.Integer(), nullable=False),
    sa.Column('source_container', sa.String(length=40), nullable=True),
    sa.Column('source_codec', sa.String(length=20), nullable=True),
    sa.Column('has_audio', sa.Boolean(), nullable=False),
    sa.Column('playback_path', sa.String(length=300), nullable=True),
    sa.Column('duration_s', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='uploaded', nullable=False),
    sa.Column('step', sa.String(length=12), nullable=True),
    sa.Column('fail_code', sa.String(length=20), nullable=True),
    sa.Column('fail_detail', sa.String(length=300), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('ready_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('deleted_at', app.db.types.UtcDateTime(), nullable=True),
    sa.CheckConstraint("(status = 'failed') = (fail_code IS NOT NULL)", name=op.f('ck_clip_failed_has_code')),
    sa.CheckConstraint("fail_code IS NULL OR fail_code IN ('unsupported_file', 'too_long', 'transcode_failed', 'ai_failed', 'ai_invalid_output')", name=op.f('ck_clip_fail_code')),
    sa.CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name=op.f('ck_clip_status')),
    sa.CheckConstraint("step IS NULL OR step IN ('transcode', 'transcribe', 'sample', 'draft')", name=op.f('ck_clip_step')),
    sa.CheckConstraint('duration_s > 0 AND duration_s <= 120.5', name=op.f('ck_clip_duration')),
    sa.CheckConstraint('has_audio IN (0, 1)', name=op.f('ck_clip_has_audio_bool')),
    sa.CheckConstraint('ordinal BETWEEN 1 AND 3', name=op.f('ck_clip_ordinal')),
    sa.CheckConstraint('original_size_bytes <= 209715200', name=op.f('ck_clip_size_limit')),
    sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], name=op.f('fk_clip_dog_id_dog'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['session.id'], name=op.f('fk_clip_session_id_session'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clip'))
    )
    op.create_index('ix_clip_dog', 'clip', ['dog_id'], unique=False)
    op.create_index('ix_clip_status', 'clip', ['status'], unique=False)
    op.create_index('uq_clip_session_ordinal', 'clip', ['session_id', 'ordinal'], unique=True, sqlite_where=sa.text('deleted_at IS NULL'))
    op.create_index('uq_clip_session_req', 'clip', ['session_id', 'client_request_id'], unique=True, sqlite_where=sa.text('client_request_id IS NOT NULL'))
    op.create_table('cost_ledger',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('purpose', sa.String(length=16), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=60), nullable=False),
    sa.Column('tokens_in', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('tokens_out', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('audio_s', sa.Float(), nullable=True),
    sa.Column('usd_micros', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=True),
    sa.Column('session_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("purpose IN ('transcribe', 'draft', 'check', 'qa_select', 'spike')", name=op.f('ck_cost_ledger_purpose')),
    sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], name=op.f('fk_cost_ledger_dog_id_dog'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['session.id'], name=op.f('fk_cost_ledger_session_id_session'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_ledger')),
    sqlite_autoincrement=True
    )
    op.create_index('ix_cost_purpose_time', 'cost_ledger', ['purpose', 'created_at'], unique=False)
    op.create_index('ix_cost_session', 'cost_ledger', ['session_id'], unique=False)
    op.create_table('fact',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=True),
    sa.Column('created_by', sa.String(length=32), nullable=True),
    sa.Column('situation', sa.String(length=14), nullable=False),
    sa.Column('behavior', sa.String(length=280), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('origin', sa.String(length=14), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='draft', nullable=False),
    sa.Column('merged', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('flags', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('ai_model', sa.String(length=60), nullable=True),
    sa.Column('confirmed_by', sa.String(length=32), nullable=True),
    sa.Column('confirmed_role', sa.String(length=10), nullable=True),
    sa.Column('confirmed_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('deleted_at', app.db.types.UtcDateTime(), nullable=True),
    sa.Column('deleted_by', sa.String(length=32), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('updated_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("(status = 'confirmed') = (confirmed_at IS NOT NULL AND confirmed_role IS NOT NULL)", name=op.f('ck_fact_confirmed_triplet')),
    sa.CheckConstraint("status = 'confirmed' OR (confirmed_at IS NULL AND confirmed_role IS NULL)", name=op.f('ck_fact_unconfirmed_clear')),
    sa.CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name=op.f('ck_fact_deleted_pair')),
    sa.CheckConstraint("confirmed_role IS NULL OR confirmed_role IN ('staff', 'volunteer')", name=op.f('ck_fact_confirmed_role')),
    sa.CheckConstraint("merged = 1 OR (origin = 'ai_unchanged' AND status = 'draft')", name=op.f('ck_fact_unmerged_only_ai_drafts')),
    sa.CheckConstraint("origin IN ('ai_unchanged', 'human_edited', 'human_added')", name=op.f('ck_fact_origin')),
    sa.CheckConstraint("situation <> 'children_cats' OR status <> 'confirmed' OR confirmed_role = 'staff'", name=op.f('ck_fact_situation8_staff_only')),
    sa.CheckConstraint("situation IN ('new_person', 'handling', 'leash_walk', 'other_dog', 'food_toys', 'alone_time', 'indoors_rest', 'children_cats')", name=op.f('ck_fact_situation')),
    sa.CheckConstraint("source <> 'staff_note' OR origin = 'human_added'", name=op.f('ck_fact_staff_note_origin')),
    sa.CheckConstraint("source IN ('clip', 'narration', 'staff_note')", name=op.f('ck_fact_source')),
    sa.CheckConstraint("status IN ('draft', 'confirmed', 'deleted')", name=op.f('ck_fact_status')),
    sa.CheckConstraint('merged IN (0, 1)', name=op.f('ck_fact_merged_bool')),
    sa.ForeignKeyConstraint(['confirmed_by'], ['member.id'], name=op.f('fk_fact_confirmed_by_member'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['member.id'], name=op.f('fk_fact_created_by_member'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['member.id'], name=op.f('fk_fact_deleted_by_member'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], name=op.f('fk_fact_dog_id_dog'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['session.id'], name=op.f('fk_fact_session_id_session'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fact'))
    )
    op.create_index('ix_fact_created_by', 'fact', ['created_by'], unique=False)
    op.create_index('ix_fact_dog_status_sit', 'fact', ['dog_id', 'status', 'situation'], unique=False)
    op.create_index('ix_fact_session', 'fact', ['session_id'], unique=False)
    op.create_table('fact_evidence',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('fact_id', sa.String(length=32), nullable=False),
    sa.Column('clip_id', sa.String(length=32), nullable=False),
    sa.Column('start_s', sa.Float(), nullable=False),
    sa.Column('end_s', sa.Float(), nullable=False),
    sa.CheckConstraint('end_s > start_s AND round(end_s - start_s, 6) >= 1.0 AND round(end_s - start_s, 6) <= 60.0', name=op.f('ck_fact_evidence_length')),
    sa.CheckConstraint('start_s >= 0', name=op.f('ck_fact_evidence_start_nonneg')),
    sa.ForeignKeyConstraint(['clip_id'], ['clip.id'], name=op.f('fk_fact_evidence_clip_id_clip'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['fact_id'], ['fact.id'], name=op.f('fk_fact_evidence_fact_id_fact'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fact_evidence'))
    )
    op.create_index('ix_evidence_clip', 'fact_evidence', ['clip_id'], unique=False)
    op.create_index('ix_evidence_fact', 'fact_evidence', ['fact_id'], unique=False)
    op.create_table('qa_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('dog_id', sa.String(length=32), nullable=False),
    sa.Column('ip_hash', sa.String(length=64), nullable=False),
    sa.Column('cookie_id', sa.String(length=32), nullable=False),
    sa.Column('question', sa.String(length=300), nullable=True),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('fact_ids', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('dropped_ids', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('ledger_id', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('created_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("outcome IN ('answered', 'not_observed', 'health_redirect', 'error')", name=op.f('ck_qa_log_outcome')),
    sa.ForeignKeyConstraint(['dog_id'], ['dog.id'], name=op.f('fk_qa_log_dog_id_dog'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ledger_id'], ['cost_ledger.id'], name=op.f('fk_qa_log_ledger_id_cost_ledger'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qa_log')),
    sqlite_autoincrement=True
    )
    op.create_index('ix_qa_cookie_time', 'qa_log', ['cookie_id', 'created_at'], unique=False)
    op.create_index('ix_qa_dog', 'qa_log', ['dog_id'], unique=False)
    op.create_index('ix_qa_ip_time', 'qa_log', ['ip_hash', 'created_at'], unique=False)
    op.create_table('segment',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('clip_id', sa.String(length=32), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('start_s', sa.Float(), nullable=False),
    sa.Column('end_s', sa.Float(), nullable=False),
    sa.CheckConstraint('end_s > start_s', name=op.f('ck_segment_range')),
    sa.ForeignKeyConstraint(['clip_id'], ['clip.id'], name=op.f('fk_segment_clip_id_clip'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_segment')),
    sqlite_autoincrement=True
    )
    op.create_index('uq_segment_clip_idx', 'segment', ['clip_id', 'idx'], unique=True)
    op.create_table('transcript_segment',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('clip_id', sa.String(length=32), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('start_s', sa.Float(), nullable=False),
    sa.Column('end_s', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('lang', sa.String(length=8), nullable=True),
    sa.CheckConstraint('end_s > start_s', name=op.f('ck_transcript_segment_range')),
    sa.CheckConstraint('start_s >= 0', name=op.f('ck_transcript_segment_start_nonneg')),
    sa.ForeignKeyConstraint(['clip_id'], ['clip.id'], name=op.f('fk_transcript_segment_clip_id_clip'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transcript_segment')),
    sqlite_autoincrement=True
    )
    op.create_index('uq_tseg_clip_idx', 'transcript_segment', ['clip_id', 'idx'], unique=True)
    op.create_table('playback_event',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('fact_id', sa.String(length=32), nullable=False),
    sa.Column('evidence_id', sa.String(length=32), nullable=False),
    sa.Column('member_id', sa.String(length=32), nullable=False),
    sa.Column('start_s', sa.Float(), nullable=False),
    sa.Column('end_s', sa.Float(), nullable=False),
    sa.Column('watched_s', sa.Float(), nullable=False),
    sa.Column('completed_at', app.db.types.UtcDateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.ForeignKeyConstraint(['evidence_id'], ['fact_evidence.id'], name=op.f('fk_playback_event_evidence_id_fact_evidence'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['fact_id'], ['fact.id'], name=op.f('fk_playback_event_fact_id_fact'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['member_id'], ['member.id'], name=op.f('fk_playback_event_member_id_member'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_playback_event')),
    sa.UniqueConstraint('evidence_id', 'member_id', name='uq_playback_event_evidence_member'),
    sqlite_autoincrement=True
    )
    op.create_index('ix_pbe_fact_member', 'playback_event', ['fact_id', 'member_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pbe_fact_member', table_name='playback_event')
    op.drop_table('playback_event')
    op.drop_index('uq_tseg_clip_idx', table_name='transcript_segment')
    op.drop_table('transcript_segment')
    op.drop_index('uq_segment_clip_idx', table_name='segment')
    op.drop_table('segment')
    op.drop_index('ix_qa_ip_time', table_name='qa_log')
    op.drop_index('ix_qa_dog', table_name='qa_log')
    op.drop_index('ix_qa_cookie_time', table_name='qa_log')
    op.drop_table('qa_log')
    op.drop_index('ix_evidence_fact', table_name='fact_evidence')
    op.drop_index('ix_evidence_clip', table_name='fact_evidence')
    op.drop_table('fact_evidence')
    op.drop_index('ix_fact_session', table_name='fact')
    op.drop_index('ix_fact_dog_status_sit', table_name='fact')
    op.drop_index('ix_fact_created_by', table_name='fact')
    op.drop_table('fact')
    op.drop_index('ix_cost_session', table_name='cost_ledger')
    op.drop_index('ix_cost_purpose_time', table_name='cost_ledger')
    op.drop_table('cost_ledger')
    op.drop_index('uq_clip_session_req', table_name='clip', sqlite_where=sa.text('client_request_id IS NOT NULL'))
    op.drop_index('uq_clip_session_ordinal', table_name='clip', sqlite_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_clip_status', table_name='clip')
    op.drop_index('ix_clip_dog', table_name='clip')
    op.drop_table('clip')
    op.drop_index('ix_session_status', table_name='session')
    op.drop_index('ix_session_member', table_name='session')
    op.drop_index('ix_session_dog', table_name='session')
    op.drop_table('session')
    op.drop_index('uq_dog_slug', table_name='dog')
    op.drop_index('ix_dog_org_status', table_name='dog')
    op.drop_table('dog')
    op.drop_index('uq_member_email', table_name='member')
    op.drop_index('ix_member_org', table_name='member')
    op.drop_table('member')
    op.drop_table('org')
    op.drop_index('uq_job_dedupe', table_name='job', sqlite_where=sa.text("status IN ('queued', 'running')"))
    op.drop_index('ix_job_dog', table_name='job')
    op.drop_index('ix_job_clip', table_name='job')
    op.drop_index('ix_job_claim', table_name='job')
    op.drop_table('job')
