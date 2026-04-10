class Animal : Object {
  speak [ |
    _ := 'Some sound' print.
  ]
}
class Dog : Animal {
  speak [ |
    _ := 'Woof' print.
  ]
  run [ |
    _ := self speak.
    _ := super speak.
  ]
}
class Main : Object {
  run [ |
    d := Dog new.
    _ := d run.
  ]
}
