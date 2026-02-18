-- Fix lowercase enum values to uppercase
-- Run this in PostgreSQL to fix existing data

-- Fix scope_type lowercase -> uppercase
UPDATE availability_rules 
SET scope_type = 'PRODUCT' 
WHERE scope_type = 'product';

UPDATE availability_rules 
SET scope_type = 'CATEGORY' 
WHERE scope_type = 'category';

-- Verify the fix
SELECT scope_type, COUNT(*) 
FROM availability_rules 
GROUP BY scope_type;
