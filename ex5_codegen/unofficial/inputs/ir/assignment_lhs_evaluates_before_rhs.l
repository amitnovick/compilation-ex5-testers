array IntArray = int[]; IntArray a := nil; int idx(){ a[0] := 5; return 0; } int rhs(){ return a[0]; } void main(){ a := new int[1]; a[0] := 0; a[idx()] := rhs(); PrintInt(a[0]); }
