class Base { int go(){ return 1; } } class Child extends Base { int go(){ return 2; } } void main(){ Base b := new Child; PrintInt(b.go()); }
