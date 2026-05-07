class Counter { int i := 32767; }

Counter c := nil;

int inc()
{
    c.i := c.i + 1;
    return 0;
}

int dec()
{
    c.i := c.i - 1;
    return 9;
}

int observe(int first, int second)
{
    return c.i;
}

void main()
{
    c := new Counter;
    PrintInt(observe(inc(), dec()));
}
