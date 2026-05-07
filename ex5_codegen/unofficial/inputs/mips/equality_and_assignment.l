class Cell { int value := 1; }
array IntArray = int[];

void main()
{
    Cell c1 := new Cell;
    Cell c2 := c1;
    IntArray a1 := new int[1];
    IntArray a2 := a1;
    string s := "ab" + "cd";
    PrintInt(c1 = c2);
    PrintInt(a1 = a2);
    PrintInt(s = "abcd");
    c1.value := 5;
    PrintInt(c2.value);
}
