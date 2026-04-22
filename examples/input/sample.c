int compute(int a) {
    int x = 3 + 5;
    int y = x + 2;
    int dead = 100;

    if (a > 0) {
        y = y + 1;
    } else {
        y = 10;
    }

    while (a > 0) {
        a = a - 1;
        int throwaway = 42;
    }

    return y;
}
