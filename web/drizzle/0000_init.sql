CREATE TABLE `datasets` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`contract_json` text NOT NULL,
	`contract_version` text NOT NULL,
	`contract_hash` text NOT NULL,
	`split_seed` integer DEFAULT 42 NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `decisions` (
	`decision_id` text PRIMARY KEY NOT NULL,
	`request_id` text,
	`text` text NOT NULL,
	`source` text,
	`dataset_id` text,
	`row_id` text,
	`probability` real NOT NULL,
	`predicted_label` integer NOT NULL,
	`final_label` integer,
	`resolved_by` text NOT NULL,
	`action` text NOT NULL,
	`model_version` text NOT NULL,
	`policy_version` text NOT NULL,
	`reason` text,
	`latency_ms` integer NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `decisions_request` ON `decisions` (`request_id`);--> statement-breakpoint
CREATE INDEX `decisions_model` ON `decisions` (`model_version`,`created_at`);--> statement-breakpoint
CREATE TABLE `feedback` (
	`feedback_id` text PRIMARY KEY NOT NULL,
	`decision_id` text NOT NULL,
	`model_version` text NOT NULL,
	`label` integer NOT NULL,
	`category` text,
	`labeler` text NOT NULL,
	`reason` text,
	`dataset_id` text NOT NULL,
	`row_id` text NOT NULL,
	`event_id` text NOT NULL,
	`training_eligible` integer NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`decision_id`) REFERENCES `decisions`(`decision_id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `feedback_decision` ON `feedback` (`decision_id`);--> statement-breakpoint
CREATE TABLE `label_events` (
	`seq` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`event_id` text NOT NULL,
	`dataset_id` text NOT NULL,
	`row_id` text NOT NULL,
	`label` integer,
	`category` text,
	`labeler` text NOT NULL,
	`at` text NOT NULL,
	`reason` text,
	`kind` text NOT NULL,
	`contract_version` text NOT NULL,
	`decision_id` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `label_events_event_id_unique` ON `label_events` (`event_id`);--> statement-breakpoint
CREATE INDEX `events_row` ON `label_events` (`dataset_id`,`row_id`);--> statement-breakpoint
CREATE TABLE `rows` (
	`dataset_id` text NOT NULL,
	`id` text NOT NULL,
	`text` text NOT NULL,
	`category` text,
	`split` text DEFAULT 'unassigned' NOT NULL,
	`source` text,
	`group_id` text,
	`created_at` text NOT NULL,
	PRIMARY KEY(`dataset_id`, `id`),
	FOREIGN KEY (`dataset_id`) REFERENCES `datasets`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `rows_split` ON `rows` (`dataset_id`,`split`);--> statement-breakpoint
CREATE TABLE `snapshots` (
	`id` text PRIMARY KEY NOT NULL,
	`dataset_id` text NOT NULL,
	`snapshot_hash` text NOT NULL,
	`manifest_json` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`dataset_id`) REFERENCES `datasets`(`id`) ON UPDATE no action ON DELETE no action
);
