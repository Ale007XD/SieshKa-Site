"""Test script for subcategories functionality"""
import sys
sys.path.insert(0, 'C:/SieshKa-Site-Prod/SieshKa-Site-final')

from app.models import Category, Product, MenuPeriod
from app.db import SessionLocal, engine
from sqlalchemy import text

def test_category_model():
    """Test that Category model has parent/children relationships"""
    print("Testing Category model with subcategories...")
    
    with SessionLocal() as db:
        # Check if parent_id column exists in database
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'categories' AND column_name = 'parent_id'
        """))
        
        if result.fetchone():
            print("✓ parent_id column exists in database")
        else:
            print("✗ parent_id column NOT found in database - run migrations!")
            return False
        
        # Test model relationships
        print("\nTesting model relationships...")
        
        # Create test data
        try:
            # Create parent category
            parent = Category(
                name="Test Parent Category",
                sort=1,
                is_active=True,
                menu_period=MenuPeriod.both
            )
            db.add(parent)
            db.flush()
            
            # Create child category
            child = Category(
                name="Test Child Category",
                sort=1,
                is_active=True,
                menu_period=MenuPeriod.both,
                parent_id=parent.id
            )
            db.add(child)
            db.flush()
            
            # Test relationships
            assert parent.children, "Parent should have children"
            assert len(parent.children) == 1, "Parent should have 1 child"
            assert parent.children[0].name == "Test Child Category", "Child name should match"
            
            assert child.parent, "Child should have parent"
            assert child.parent.name == "Test Parent Category", "Parent name should match"
            
            print("✓ Self-referential relationships work correctly")
            
            # Clean up
            db.delete(child)
            db.delete(parent)
            db.commit()
            
            print("✓ Test data cleaned up")
            return True
            
        except Exception as e:
            db.rollback()
            print(f"✗ Error testing relationships: {e}")
            return False

def test_hierarchy_methods():
    """Test helper methods like get_hierarchy_path and is_leaf_category"""
    print("\nTesting hierarchy helper methods...")
    
    with SessionLocal() as db:
        try:
            # Create hierarchy: Grandparent -> Parent -> Child
            grandparent = Category(name="Grandparent", menu_period=MenuPeriod.both)
            db.add(grandparent)
            db.flush()
            
            parent = Category(name="Parent", menu_period=MenuPeriod.both, parent_id=grandparent.id)
            db.add(parent)
            db.flush()
            
            child = Category(name="Child", menu_period=MenuPeriod.both, parent_id=parent.id)
            db.add(child)
            db.flush()
            
            # Test is_leaf_category
            assert not grandparent.is_leaf_category(), "Grandparent should not be leaf"
            assert not parent.is_leaf_category(), "Parent should not be leaf"
            assert child.is_leaf_category(), "Child should be leaf"
            print("✓ is_leaf_category() works correctly")
            
            # Test get_hierarchy_path
            assert grandparent.get_hierarchy_path() == "Grandparent"
            assert parent.get_hierarchy_path() == "Grandparent > Parent"
            assert child.get_hierarchy_path() == "Grandparent > Parent > Child"
            print("✓ get_hierarchy_path() works correctly")
            
            # Clean up
            db.delete(child)
            db.delete(parent)
            db.delete(grandparent)
            db.commit()
            
            return True
            
        except Exception as e:
            db.rollback()
            print(f"✗ Error testing hierarchy methods: {e}")
            return False

def test_circular_reference_prevention():
    """Test that circular references are prevented"""
    print("\nTesting circular reference prevention...")
    
    with SessionLocal() as db:
        try:
            # Create a chain: A -> B -> C
            cat_a = Category(name="Category A", menu_period=MenuPeriod.both)
            db.add(cat_a)
            db.flush()
            
            cat_b = Category(name="Category B", menu_period=MenuPeriod.both, parent_id=cat_a.id)
            db.add(cat_b)
            db.flush()
            
            cat_c = Category(name="Category C", menu_period=MenuPeriod.both, parent_id=cat_b.id)
            db.add(cat_c)
            db.flush()
            
            # Try to make A child of C (circular)
            try:
                cat_a.parent_id = cat_c.id
                db.flush()
                print("✗ Circular reference was allowed (should be prevented)")
                return False
            except:
                db.rollback()
                print("✓ Circular reference correctly prevented by database")
            
            # Clean up
            with SessionLocal() as db2:
                for name in ["Category C", "Category B", "Category A"]:
                    cat = db2.query(Category).filter_by(name=name).first()
                    if cat:
                        db2.delete(cat)
                db2.commit()
            
            return True
            
        except Exception as e:
            print(f"✗ Error testing circular reference: {e}")
            return False

if __name__ == "__main__":
    print("=" * 60)
    print("SUBCATEGORIES FUNCTIONALITY TESTS")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("Category Model", test_category_model()))
        results.append(("Hierarchy Methods", test_hierarchy_methods()))
        results.append(("Circular Reference Prevention", test_circular_reference_prevention()))
    except Exception as e:
        print(f"\n✗ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    sys.exit(0 if all_passed else 1)
