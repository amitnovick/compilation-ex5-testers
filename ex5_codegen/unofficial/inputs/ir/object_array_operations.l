class Box { int value := 4; }
array IntArray = int[];

void main()
{
    Box b := new Box;
    IntArray values := new int[2];
    values[0] := b.value;
    values[1] := values[0] + 3;
    PrintInt(values[1]);
}
