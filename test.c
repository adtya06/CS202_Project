#include <stdio.h> 

void foo(){
    printf("Hellow"); 
}

int master_optimizer_test() {
    int a;
    int b;
    int c;
    int d;
    int e;
    int dead_var;

    // 1. Constant Propagation Trigger
    a = 10;
    
    // 2. Constant Folding Trigger
    b = 20 + 3*a;

    // 3. Propagation + Folding Combined
    // 'a' and 'b' propagate down, turning this into "10 + 50"
    // The secondary folding pass will then crush it into "60"
    c = a + b;
    foo();

    // 4. Strength Reduction Trigger
    // CPU-heavy multiplication and division by 2
    d = c * 2;
    e = d / 2;

    a = a*2 ; 

    // 5. Dead Code Elimination Trigger
    // Assigned, overwritten, and never used before the return.
    dead_var = 999;
    dead_var = 888;
    if (a == 10)
    printf("%d" , &e); 
    else 
    printf("%d" , &a);

    return e;

    // 6. Unreachable Code Trigger
    // Structurally severed from the execution path by the return statement above.
    c = 0;
    d = 0;
}