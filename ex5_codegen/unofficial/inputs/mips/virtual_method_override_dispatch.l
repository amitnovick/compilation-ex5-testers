class Parent { int go(){ return 1; } } class Child extends Parent { int go(){ return 2; } } void main(){ Parent p := new Child; PrintInt(p.go()); }
