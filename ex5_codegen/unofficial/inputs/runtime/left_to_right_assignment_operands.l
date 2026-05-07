array IntArray = int[]; IntArray a := nil; int x := 0; int idx(){ x := 5; return 0; } int rhs(){ return x; } void main(){ a := new int[1]; a[idx()] := rhs(); PrintInt(a[0]); }
