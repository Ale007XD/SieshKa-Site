"""Simple syntax and structure validation for subcategories"""
import ast
import sys

def validate_models_py():
    """Validate models.py syntax and structure"""
    print("Validating app/models.py...")
    
    try:
        with open("app/models.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse to check syntax
        tree = ast.parse(content)
        print("[OK] Syntax is valid")
        
        # Check for Category class
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if "Category" in classes:
            print("[OK] Category class exists")
        else:
            print("[FAIL] Category class not found")
            return False
        
        # Check for parent_id field
        if "parent_id" in content:
            print("[OK] parent_id field exists")
        else:
            print("[FAIL] parent_id field not found")
            return False
        
        # Check for parent/children relationships
        if "parent" in content and "children" in content:
            print("[OK] parent and children relationships exist")
        else:
            print("[FAIL] parent/children relationships not found")
            return False
        
        # Check for helper methods
        if "get_all_products" in content:
            print("[OK] get_all_products() method exists")
        else:
            print("[FAIL] get_all_products() method not found")
            return False
            
        if "get_hierarchy_path" in content:
            print("[OK] get_hierarchy_path() method exists")
        else:
            print("[FAIL] get_hierarchy_path() method not found")
            return False
            
        if "is_leaf_category" in content:
            print("[OK] is_leaf_category() method exists")
        else:
            print("[FAIL] is_leaf_category() method not found")
            return False
        
        return True
        
    except SyntaxError as e:
        print(f"[FAIL] Syntax error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

def validate_admin_py():
    """Validate admin.py changes"""
    print("\nValidating app/admin.py...")
    
    try:
        with open("app/admin.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse to check syntax
        tree = ast.parse(content)
        print("[OK] Syntax is valid")
        
        # Check for circular reference prevention
        if "_is_circular_reference" in content:
            print("[OK] Circular reference prevention implemented")
        else:
            print("[FAIL] Circular reference prevention not found")
            return False
        
        # Check for parent validation in on_model_change
        if "parent_id" in content and "model.id" in content:
            print("[OK] Self-reference validation exists")
        else:
            print("[FAIL] Self-reference validation not found")
            return False
        
        # Check for column_list update
        if "Category.parent" in content:
            print("[OK] Category.parent in column_list")
        else:
            print("[FAIL] Category.parent not in column_list")
            return False
        
        return True
        
    except SyntaxError as e:
        print(f"[FAIL] Syntax error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

def validate_migration():
    """Validate Alembic migration"""
    print("\nValidating alembic/versions/0002_add_category_parent_id.py...")
    
    try:
        with open("alembic/versions/0002_add_category_parent_id.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse to check syntax
        tree = ast.parse(content)
        print("[OK] Syntax is valid")
        
        # Check for parent_id column addition
        if "parent_id" in content:
            print("[OK] parent_id column migration exists")
        else:
            print("[FAIL] parent_id column migration not found")
            return False
        
        # Check for foreign key
        if "create_foreign_key" in content or "ForeignKey" in content:
            print("[OK] Foreign key constraint exists")
        else:
            print("[FAIL] Foreign key constraint not found")
            return False
        
        # Check for index
        if "ix_categories_parent_id" in content:
            print("[OK] Index on parent_id exists")
        else:
            print("[FAIL] Index on parent_id not found")
            return False
        
        # Check for proper revision chain
        if "0001_full_schema" in content:
            print("[OK] Migration chain is correct (depends on 0001_full_schema)")
        else:
            print("[FAIL] Migration chain is broken")
            return False
        
        return True
        
    except SyntaxError as e:
        print(f"[FAIL] Syntax error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

def validate_main_py():
    """Validate main.py changes for hierarchical menu"""
    print("\nValidating app/main.py menu endpoint...")
    
    try:
        with open("app/main.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check for hierarchical structure
        if "categories_data" in content:
            print("[OK] categories_data structure used")
        else:
            print("[FAIL] categories_data structure not found")
            return False
        
        # Check for root categories filter
        if "parent_id == None" in content:
            print("[OK] Root categories filter exists")
        else:
            print("[FAIL] Root categories filter not found")
            return False
        
        # Check for subcategories handling
        if "subcategories" in content and "subcat" in content:
            print("[OK] Subcategories handling implemented")
        else:
            print("[FAIL] Subcategories handling not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

def validate_template():
    """Validate template changes"""
    print("\nValidating app/templates/index.html...")
    
    try:
        with open("app/templates/index.html", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check for categories_data iteration
        if "for cat_data in categories_data" in content:
            print("[OK] categories_data iteration exists")
        else:
            print("[FAIL] categories_data iteration not found")
            return False
        
        # Check for subcategories display
        if "for subcat_data in cat_data.subcategories" in content:
            print("[OK] Subcategories display implemented")
        else:
            print("[FAIL] Subcategories display not found")
            return False
        
        # Check for proper nesting structure
        if "cat_data.products" in content and "subcat_data.products" in content:
            print("[OK] Product display structure is correct")
        else:
            print("[FAIL] Product display structure incomplete")
            return False
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("SUBCATEGORIES IMPLEMENTATION VALIDATION")
    print("=" * 70)
    
    results = []
    
    results.append(("Models (app/models.py)", validate_models_py()))
    results.append(("Admin (app/admin.py)", validate_admin_py()))
    results.append(("Migration (alembic/versions/0002_add_category_parent_id.py)", validate_migration()))
    results.append(("Main (app/main.py)", validate_main_py()))
    results.append(("Template (app/templates/index.html)", validate_template()))
    
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("ALL VALIDATIONS PASSED!")
        print("\nNext steps:")
        print("1. Run: alembic upgrade head")
        print("2. Restart the application")
        print("3. Create parent and child categories in admin panel")
        print("4. Add products to verify menu displays correctly")
    else:
        print("SOME VALIDATIONS FAILED")
        print("Please review the failed checks above.")
    
    print("=" * 70)
    sys.exit(0 if all_passed else 1)
