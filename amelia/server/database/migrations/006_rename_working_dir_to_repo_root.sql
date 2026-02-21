-- Rename working_dir to repo_root if the column exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'working_dir'
    ) THEN
        ALTER TABLE profiles RENAME COLUMN working_dir TO repo_root;
    END IF;
END $$;
