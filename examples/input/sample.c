int compute(int a, int b) {
    int x = 3 + 5;
    int y = x + 2;
    int cse1 = a + b;
    int cse2 = a + b;
    int b2 = b + 1;
    int shift1 = a * 8;
    int shift2 = b2 * 4;
    int dead = 100;

    if (a > 0) {
        y = y + 1;
    } else {
        y = 10;
    }

    int sum = 0;
    int i = 0;
    for (; i < 3; i = i + 1) {
        sum = sum + 2;
    }
    y = y + sum + i;

    while (b > 0) {
        b = b - 1;
        int throwaway = 42;
    }

    return y + cse2 + shift1 + shift2;
    int unreachable = 88;
}