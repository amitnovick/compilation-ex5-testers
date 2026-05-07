int combine(int a, int b, int c, int d)
{
    int left := a + b;
    int right := c + d;
    int product := left * right;
    return product - a;
}

void main()
{
    PrintInt(combine(1, 2, 3, 4));
}
